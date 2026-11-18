"""Score every creator 0–100 with a feature breakdown and a one-line reason.

    python -m feng_workers.scoring              # all creators
    python -m feng_workers.scoring --only-unscored

Features (each 0–1, or null when the data can't support it):
  locality         creator's city vs each location's area + local keywords in captions (estimate)
  niche            caption embeddings vs the brand corpus (cosine), scaled across creators
  engagement       (likes + comments) / followers, against config's target rate
  comment_quality  PROXY: comments per like, until comment text is collected
  cadence          posts per week over the recent window
  brand_fit        Claude's 0–10 judgement / 10 (AI_MODE=llm only)

score = 100 × weighted average of the known features (weights: config/scoring.json).
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from .config import load_config
from .llm import LLM, ai_mode, load_prompt, to_json, untrusted

log = logging.getLogger(__name__)
FEATURES = ("locality", "niche", "engagement", "comment_quality", "cadence", "brand_fit")


class BrandFit(BaseModel):
    fit_0_10: int = Field(ge=0, le=10)
    reason: str = Field(min_length=10, max_length=160)


@dataclass
class CreatorData:
    id: str
    handle: str
    platform: str
    city: str | None
    followers: int | None
    bio: str | None = None
    posts: list[dict] = field(default_factory=list)   # newest first
    niche_raw: float | None = None


def _clip(x: float | None) -> float | None:
    return None if x is None else round(max(0.0, min(1.0, x)), 2)


# --------------------------------------------------------------------------- data

def load_creators(conn, cfg: dict, only_unscored: bool = False) -> list[CreatorData]:
    n = cfg["recent_posts_for_scoring"]
    rows = conn.execute(
        f"select id, handle, platform, city, followers, bio from creators {'where score is null' if only_unscored else ''} order by handle"
    ).fetchall()
    creators = {str(r[0]): CreatorData(str(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in rows}
    if not creators:
        return []
    for cid, url, caption, posted_at, likes, comments in conn.execute(
        """
        select creator_id, url, caption, posted_at, likes, comments from (
          select p.*, row_number() over (partition by creator_id order by posted_at desc nulls last) rn
          from creator_posts p where creator_id = any(%s)) t
        where rn <= %s order by creator_id, posted_at desc nulls last
        """,
        (list(creators), n),
    ):
        creators[str(cid)].posts.append(
            {"url": url, "caption": caption, "posted_at": posted_at, "likes": likes, "comments": comments})

    # Niche: per post, best cosine similarity to any brand-corpus row embedded by
    # the same model; per creator, mean of the top-k posts.
    k = cfg["niche_top_k_posts"]
    for cid, sim in conn.execute(
        """
        with s as (
          select p.creator_id, max(1 - (p.embedding <=> b.embedding)) as sim
          from creator_posts p
          join brand_corpus b on b.embedding_model = p.embedding_model
          where p.embedding is not null and b.embedding is not null and p.creator_id = any(%s)
            and vector_dims(p.embedding) = vector_dims(b.embedding)
          group by p.id, p.creator_id
        ), r as (select *, row_number() over (partition by creator_id order by sim desc) rn from s)
        select creator_id, avg(sim) from r where rn <= %s group by creator_id
        """,
        (list(creators), k),
    ):
        creators[str(cid)].niche_raw = float(sim)
    return list(creators.values())


def load_locations(conn) -> list[dict]:
    return [{"slug": s, "name": n, "cities": [c.lower() for c in cities] + [n.lower()]}
            for s, n, cities in conn.execute("select slug, name, creator_cities from locations where is_active")]


# --------------------------------------------------------------------------- features

def _local_hit(text: str, keywords: list[str], exclude: list[str]) -> bool:
    """A keyword counts unless an exclusion phrase also appears (大湾区 contains 湾区)."""
    text = text.lower()
    return any(k in text for k in keywords) and not any(x in text for x in exclude)


def locality(c: CreatorData, locations: list[dict], cfg: dict) -> float | None:
    """Estimate from the creator's city, bio and captions. The bio can also pull
    the score down: a bio that names a place outside the area (moved away,
    the other 湾区) caps it at outside_area."""
    lc = cfg["locality"]
    city = (c.city or "").strip().lower()
    match = next((l for l in locations if city and city in l["cities"]), None)
    if match is None and not city and not c.posts and not c.bio:
        return None
    slugs = [match["slug"]] if match else list(cfg["locality_keywords"])
    keywords = [k for s in slugs for k in cfg["locality_keywords"].get(s, [])]
    exclude = [x.lower() for s in slugs for x in cfg.get("locality_exclude", {}).get(s, [])]
    if match:
        base = lc["home_city"] if city == match["name"].lower() else lc["area_city"]
    else:
        base = lc["outside_area"]
    if c.bio and any(x in c.bio.lower() for x in exclude):
        return _clip(min(base, lc["outside_area"]))
    texts = [p["caption"] or "" for p in c.posts] + ([c.bio] if c.bio else [])
    hits = sum(1 for t in texts if _local_hit(t, keywords, exclude))
    bonus = lc["keyword_bonus_max"] * (hits / len(texts) if texts else 0)
    return _clip(base + bonus)


def engagement(c: CreatorData, cfg: dict) -> float | None:
    rates = [((p["likes"] or 0) + (p["comments"] or 0)) / c.followers
             for p in c.posts if c.followers and p["likes"] is not None]
    return _clip(sum(rates) / len(rates) / cfg["engagement_target_rate"]) if rates else None


def comment_quality(c: CreatorData, cfg: dict) -> float | None:
    likes = sum(p["likes"] or 0 for p in c.posts if p["likes"] is not None and p["comments"] is not None)
    comments = sum(p["comments"] or 0 for p in c.posts if p["likes"] is not None and p["comments"] is not None)
    return _clip(comments / likes / cfg["conversation_target_ratio"]) if likes else None


def cadence(c: CreatorData, cfg: dict, reference: datetime) -> float:
    window = cfg["cadence_window_days"]
    since = reference - timedelta(days=window)
    recent = sum(1 for p in c.posts if p["posted_at"] and p["posted_at"] >= since)
    return _clip(recent / (window / 7) / cfg["cadence_target_posts_per_week"])


def niche_scaled(creators: list[CreatorData]) -> dict[str, float | None]:
    raws = [c.niche_raw for c in creators if c.niche_raw is not None]
    lo, hi = (min(raws), max(raws)) if raws else (0, 0)
    out = {}
    for c in creators:
        if c.niche_raw is None:
            out[c.id] = None
        elif hi - lo < 1e-9:
            out[c.id] = 0.5
        else:
            out[c.id] = _clip((c.niche_raw - lo) / (hi - lo))
    return out


def combine(breakdown: dict[str, float | None], weights: dict[str, float]) -> float | None:
    known = {k: v for k, v in breakdown.items() if v is not None and weights.get(k, 0) > 0}
    total_w = sum(weights[k] for k in known)
    if not known or total_w == 0:
        return None
    return round(100 * sum(weights[k] * v for k, v in known.items()) / total_w)


LABELS = {"locality": "local audience", "niche": "food content close to our brand", "engagement": "strong engagement",
          "comment_quality": "lively comments", "cadence": "posts regularly", "brand_fit": "fits the brand"}


def template_reason(c: CreatorData, breakdown: dict) -> str:
    if not c.posts:
        return "Too few posts to judge."
    strong = [LABELS[k] for k, v in sorted(breakdown.items(), key=lambda kv: -(kv[1] or 0)) if v is not None and v >= 0.7]
    weak = [LABELS[k] for k, v in breakdown.items() if v is not None and v < 0.3]
    parts = []
    if strong:
        parts.append(", ".join(strong[:2]).capitalize())
    if weak:
        parts.append("weaker on " + weak[0])
    return ("; ".join(parts) or "Mixed signals across the data") + "."


# --------------------------------------------------------------------------- run

def brand_fit(llm: LLM, c: CreatorData, breakdown: dict, brand_notes: str) -> BrandFit:
    posts = "\n".join(untrusted("caption", p["caption"]) for p in c.posts if p["caption"])
    prompt = (
        f"Creator facts: {to_json({'handle': c.handle, 'platform': c.platform, 'city': c.city, 'followers': c.followers})}\n"
        f"Bio: {untrusted('bio', c.bio)}\n"
        f"Computed scores (0–1, null = unknown): {to_json(breakdown)}\n"
        f"Feng Hotpot brand notes:\n{brand_notes}\n\nRecent captions:\n{posts}"
    )
    return llm.structured(system=load_prompt("brand_fit"), prompt=prompt, output=BrandFit, effort="low", max_tokens=4000)


def score_all(conn, llm: LLM | None = None, *, only_unscored: bool = False, concurrency: int = 4) -> dict:
    cfg = load_config("scoring")
    weights = cfg["weights"]
    creators = load_creators(conn, cfg, only_unscored)
    if not creators:
        return {"scored": 0, "mode": ai_mode()}
    locations = load_locations(conn)
    reference = conn.execute("select coalesce(max(posted_at), now()) from creator_posts").fetchone()[0]
    niche = niche_scaled(creators)
    brand_notes = "\n".join(t for (t,) in conn.execute(
        "select text from brand_corpus where kind in ('tone', 'menu', 'location') order by kind, created_at limit 20"))

    breakdowns = {
        c.id: {"locality": locality(c, locations, cfg), "niche": niche[c.id], "engagement": engagement(c, cfg),
               "comment_quality": comment_quality(c, cfg), "cadence": cadence(c, cfg, reference), "brand_fit": None}
        for c in creators
    }

    use_llm = ai_mode() == "llm"
    if use_llm and llm is None:
        llm = LLM()

    def judge(c: CreatorData):
        if not use_llm or not c.posts:
            return c.id, None
        try:
            return c.id, brand_fit(llm, c, breakdowns[c.id], brand_notes)
        except Exception as e:   # one creator failing shouldn't stop the batch
            log.warning("brand-fit failed for @%s: %s", c.handle, e)
            return c.id, None

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        fits = dict(pool.map(judge, creators))

    now = datetime.now(timezone.utc)
    with conn.transaction():
        for c in creators:
            b = breakdowns[c.id]
            fit = fits.get(c.id)
            if fit:
                b["brand_fit"] = round(fit.fit_0_10 / 10, 2)
            reason = fit.reason if fit else template_reason(c, b)
            conn.execute(
                "update creators set score = %s, score_breakdown = %s::jsonb, score_reason = %s, scored_at = %s where id = %s",
                (combine(b, weights), to_json(b), reason, now, c.id))
    return {"scored": len(creators), "mode": "llm" if use_llm else "template",
            "brand_fit_failed": sum(1 for c in creators if use_llm and c.posts and not fits.get(c.id))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only-unscored", action="store_true")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    from .db import connect
    with connect() as conn:
        print(score_all(conn, only_unscored=args.only_unscored, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
