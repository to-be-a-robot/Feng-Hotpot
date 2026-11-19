"""Write outreach drafts for rows with generation_status = 'pending'.

    python -m feng_workers.drafts                    # drain everything pending, then exit
    python -m feng_workers.drafts --campaign <id>    # one campaign
    python -m feng_workers.drafts --watch            # keep polling (a long-running worker)

Rows are claimed with FOR UPDATE SKIP LOCKED, so several workers (or the
API's background task) can run at once without writing the same draft twice.

Safety (spec §6): captions are wrapped as untrusted data; referenced post ids
must belong to the creator; every link except the offer link is removed; the
offer link is always present exactly once, stored as {{offer_link}} so the
site URL can change later (spec §5.6). Nothing is ever sent.
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from .config import load_config
from .llm import LLM, ai_mode, load_prompt, to_json, untrusted

log = logging.getLogger(__name__)
OFFER_LINK = "{{offer_link}}"   # rendered to the real link when a draft is read (spec §5.6)
URL_RE = re.compile(r"https?://[^\s<>\"'）)】]+", re.IGNORECASE)


class Draft(BaseModel):
    message: str = Field(min_length=20, max_length=1500)
    referenced_post_ids: list[str] = Field(default_factory=list, max_length=3)


def load_context(conn, outreach_id) -> dict:
    row = conn.execute(
        """
        select o.id, o.lang, o.platform, c.id, c.handle, c.display_name, k.name, occ.name, k.offer,
               l.name, oc.code, setting('public_base_url')
        from outreach o
        join creators c on c.id = o.creator_id
        join campaigns k on k.id = o.campaign_id
        join occasions occ on occ.id = k.occasion_id
        join locations l on l.slug = k.location
        join offer_codes oc on oc.campaign_creator_id = o.campaign_creator_id and oc.kind = 'creator'
        where o.id = %s
        """,
        (outreach_id,),
    ).fetchone()
    (oid, lang, platform, creator_id, handle, display_name, campaign_name, occasion, offer,
     location_name, code, base_url) = row
    n = load_config("scoring").get("recent_posts_for_scoring", 10)
    posts = [{"id": str(pid), "caption": cap, "posted_at": str(at)[:10] if at else None}
             for pid, cap, at in conn.execute(
                 "select id, caption, posted_at from creator_posts where creator_id = %s and caption is not null "
                 "order by posted_at desc nulls last limit %s", (creator_id, n))]
    voice = [t for (t,) in conn.execute(
        "select text from brand_corpus where kind in ('tone', 'post', 'menu') and (lang is null or lang = %s) "
        "order by kind, created_at limit 12", (lang,))]
    return {
        "outreach_id": str(oid), "lang": lang, "platform": platform, "handle": handle, "display_name": display_name,
        "campaign": campaign_name, "occasion": occasion, "location": location_name,
        "offer_title": offer["title"].get(lang) or offer["title"]["en"],
        "offer_details": (offer.get("details") or {}).get(lang) or (offer.get("details") or {}).get("en"),
        "offer_url": f"{base_url}/r/{code}", "code": code, "posts": posts, "voice": voice,
    }


def clean_message(message: str, offer_url: str) -> str:
    """Remove every link except the offer link, store the offer link as the
    placeholder, and make sure it appears exactly once."""
    kept = False

    def keep_offer(m: re.Match) -> str:
        nonlocal kept
        url = m.group(0)
        trailing = url[len(url.rstrip(".,!?;:。，！？")):]
        if url.rstrip(".,!?;:。，！？") == offer_url and not kept:
            kept = True
            return OFFER_LINK + trailing
        return ""

    text = URL_RE.sub(keep_offer, message.replace(OFFER_LINK, offer_url))
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if not kept:
        text = f"{text}\n\n{OFFER_LINK}"
    return text[:2000]


def template_draft(ctx: dict) -> Draft:
    """Deterministic draft used when AI_MODE=template (no API key)."""
    name = ctx["display_name"] or "@" + ctx["handle"]
    if ctx["lang"] == "zh":
        msg = (f"{name} 你好！我们是 Feng Hotpot {ctx['location']} 店，很喜欢你最近的美食内容。"
               f"「{ctx['occasion']}」期间想邀请你和朋友来吃火锅：{ctx['offer_title']}。"
               f"专属链接：{ctx['offer_url']}\n如果发布相关内容，请按平台规定标注为合作/赠送。")
    else:
        msg = (f"Hi {name}! We're Feng Hotpot {ctx['location']} and we've enjoyed your recent food posts. "
               f"For {ctx['occasion'].lower()}, we'd love to host you and friends: {ctx['offer_title']}. "
               f"Your link: {ctx['offer_url']}\nIf you post about it, please mark it as gifted per the platform's rules.")
    return Draft(message=msg, referenced_post_ids=[])


def write_draft(llm: LLM | None, ctx: dict) -> Draft:
    if llm is None:
        return template_draft(ctx)
    valid_ids = {p["id"] for p in ctx["posts"]}
    posts = "\n".join(f'<post id="{p["id"]}" date="{p["posted_at"]}">{untrusted("text", p["caption"])}</post>'
                      for p in ctx["posts"])
    facts = {k: ctx[k] for k in ("handle", "platform", "lang", "occasion", "offer_title", "offer_details",
                                 "offer_url", "location")}
    prompt = (f"Message details: {to_json(facts)}\n\nBrand voice notes:\n" + "\n".join(f"- {v}" for v in ctx["voice"])
              + f"\n\nRecent posts:\n{posts or '(none available)'}")

    def check(d: Draft) -> list[str]:
        bad = [i for i in d.referenced_post_ids if i not in valid_ids]
        return [f"referenced_post_ids contains ids that weren't given: {bad}"] if bad else []

    return llm.structured(system=load_prompt("outreach_draft"), prompt=prompt, output=Draft,
                          effort="medium", max_tokens=8000, check=check)


def process_one(conn, llm: LLM | None, campaign_id=None) -> bool:
    """Claim one pending row and write its draft. Returns False when nothing is pending."""
    with conn.transaction():
        row = conn.execute(
            "select id from outreach where generation_status = 'pending' "
            + ("and campaign_id = %s " if campaign_id else "")
            + "order by created_at, id for update skip locked limit 1",
            (campaign_id,) if campaign_id else (),
        ).fetchone()
        if not row:
            return False
        ctx = load_context(conn, row[0])
        try:
            draft = write_draft(llm, ctx)
            text = clean_message(draft.message, ctx["offer_url"])
            refs = [i for i in dict.fromkeys(draft.referenced_post_ids) if i in {p["id"] for p in ctx["posts"]}]
            conn.execute(
                "update outreach set draft_text = %s, referenced_post_ids = %s::uuid[], has_offer_link = true, "
                "generation_status = 'ready', generation_error = null where id = %s",
                (text, refs, row[0]))
        except Exception as e:
            log.warning("draft %s failed: %s", row[0], e)
            conn.execute("update outreach set generation_status = 'failed', generation_error = %s where id = %s",
                         (str(e)[:500], row[0]))
    return True


def run(connect, *, campaign_id=None, concurrency: int = 4, llm: LLM | None = None) -> dict:
    """Drain pending drafts with `concurrency` workers, each on its own connection."""
    mode = ai_mode()
    if mode == "llm" and llm is None:
        llm = LLM()
    if mode == "template":
        llm = None

    def worker(_):
        done = 0
        with connect() as conn:
            while process_one(conn, llm, campaign_id):
                done += 1
        return done

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        total = sum(pool.map(worker, range(concurrency)))
    return {"processed": total, "mode": mode}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--watch", action="store_true", help="keep polling every 3 seconds")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    from .db import connect
    while True:
        result = run(connect, campaign_id=args.campaign, concurrency=args.concurrency)
        if result["processed"] or not args.watch:
            print(result)
        if not args.watch:
            break
        time.sleep(3)


if __name__ == "__main__":
    main()
