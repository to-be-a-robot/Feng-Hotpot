"""Generate the weekly brief for a location.

    python -m feng_workers.brief sunnyvale [--as-of 2026-12-05]

Numbers come from SQL (brief_metrics) and plain Python counting; Claude only
writes the wording (headline, highlights, review signals, 3 actions) and
labels review themes by id. A check rejects wording with numbers that aren't
in the facts, and sends it back to Claude to fix.
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .config import load_config
from .llm import LLM, ai_mode, load_prompt, to_json, untrusted


class Theme(BaseModel):
    label: str = Field(min_length=2, max_length=40)
    review_ids: list[str] = Field(min_length=1)


class Themes(BaseModel):
    themes: list[Theme] = Field(default_factory=list, max_length=5)


class Action(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    detail: str = Field(min_length=3, max_length=240)
    creator_id: str | None = None


class BriefContent(BaseModel):
    headline: str = Field(min_length=5, max_length=200)
    highlights: list[str] = Field(min_length=1, max_length=4)
    review_signals: list[str] = Field(default_factory=list, max_length=3)
    actions: list[Action] = Field(min_length=3, max_length=3)


# --------------------------------------------------------------------------- number check

NUM_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def allowed_numbers(facts) -> set[str]:
    """Every number in the facts, plus the forms the prompt allows:
    ratios as percentages and cents as dollars."""
    out: set[str] = set()

    def add(x: float):
        for v in {x, round(x), round(x, 1), round(x, 2)}:
            out.add(f"{v:g}")

    def walk(node, key=""):
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            add(float(node))
            if "rate" in key or "share" in key or key.endswith("_ratio"):
                add(node * 100)
            if key.endswith("cents"):
                add(node / 100)
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str):
            for m in NUM_RE.findall(node):   # dates and handles in the facts
                add(float(m.replace(",", "")))

    walk(facts)
    out.update(str(i) for i in range(0, 11))    # small counts like "3 actions", "2 creators"
    return out


def numbers_not_in_facts(content: BriefContent, allowed: set[str]) -> list[str]:
    texts = [content.headline, *content.highlights, *content.review_signals,
             *(a.title for a in content.actions), *(a.detail for a in content.actions)]
    bad = []
    for t in texts:
        for m in NUM_RE.findall(t):
            v = float(m.replace(",", ""))
            if f"{v:g}" not in allowed and f"{round(v):g}" not in allowed:
                bad.append(m)
    return bad


# --------------------------------------------------------------------------- generation

def week_window(conn, location: str, as_of: date | None):
    tz = conn.execute("select timezone from locations where slug = %s", (location,)).fetchone()
    if not tz:
        raise LookupError("unknown location")
    today = as_of or datetime.now(ZoneInfo(tz[0])).date()
    data_through = today - timedelta(days=1)
    return data_through - timedelta(days=data_through.weekday()), data_through


def review_summary(conn, llm: LLM | None, location: str, start: date, through: date):
    rows = conn.execute(
        """
        select r.id, r.text, r.sentiment, r.is_simulated from reviews r join locations l on l.slug = r.location
        where r.location = %s and (r.posted_at at time zone l.timezone)::date between %s and %s
        order by r.posted_at
        """, (location, start, through)).fetchall()
    if not rows:
        return None
    with_sentiment = [r for r in rows if r[2]]
    summary = {
        "review_count": len(rows),
        "positive_share": round(sum(r[2] == "positive" for r in with_sentiment) / len(with_sentiment), 2) if with_sentiment else None,
        "is_simulated": any(r[3] for r in rows),
        "themes": [],
    }
    if llm and len(rows) >= 2:
        ids = {str(r[0]) for r in rows}
        reviews = "\n".join(f'<review id="{r[0]}">{untrusted("text", r[1])}</review>' for r in rows[:200])
        themes = llm.structured(
            system=load_prompt("review_themes"), prompt=f"Reviews:\n{reviews}", output=Themes, effort="low",
            max_tokens=4000,
            check=lambda t: [f"unknown review ids in '{x.label}'" for x in t.themes if not set(x.review_ids) <= ids])
        counted = [{"label": t.label, "count": len(set(t.review_ids) & ids)} for t in themes.themes]
        summary["themes"] = sorted([t for t in counted if t["count"] >= 2], key=lambda t: -t["count"])
    return summary


def template_content(facts) -> dict:
    m = facts["metrics"]
    if not facts["top_creators"] and m["first_visits"] == 0:
        return {"headline": "No activity this week.", "highlights": [], "review_signals": [], "actions": []}
    top = facts["top_creators"][0] if facts["top_creators"] else None
    highlights = [f"{m['first_visits']} first visits and {m['return_visits']} return visits so far."]
    if top:
        highlights.append(f"{top['handle']} drove the most visits ({top['visits']}).")
    actions = []
    if top:
        actions.append({"title": f"Rebook {top['handle']}", "detail": "Top creator by visits this period.",
                        "creator_id": top["creator_id"]})
    for w in facts["waiting_for_reply"][:1]:
        actions.append({"title": f"Follow up with {w['handle']}", "detail": "Message sent, no reply yet.",
                        "creator_id": w["creator_id"]})
    actions.append({"title": "Plan the next occasion", "detail": "Pick the next occasion and shortlist creators.",
                    "creator_id": None})
    rs = facts["review_summary"]
    signals = [f"Most mentioned: {rs['themes'][0]['label']}."] if rs and rs["themes"] else []
    return {"headline": highlights[0], "highlights": highlights, "review_signals": signals, "actions": actions[:3]}


def generate(conn, location: str, *, as_of: date | None = None, llm: LLM | None = None, actor_id=None) -> dict:
    mode = ai_mode()
    if mode == "llm" and llm is None:
        llm = LLM()
    if mode == "template":
        llm = None

    week_of, data_through = week_window(conn, location, as_of)
    m = conn.execute("select brief_metrics(%s, %s, %s)", (location, week_of, data_through)).fetchone()[0]
    minutes = load_config("brief")["minutes_saved"]
    counts = m["counts_for_hours_saved"]
    metrics = {**m["metrics"], "hours_saved_estimate": round(
        (counts["creators_in_campaigns"] * minutes["research_per_creator"]
         + counts["drafts_written"] * minutes["drafting_per_message"]
         + counts["redemptions_logged"] * minutes["logging_per_redemption"]) / 60, 1)}

    start = conn.execute("select coalesce(min(start_date), %s) from campaigns where id = any(%s::uuid[])",
                         (week_of, m["campaign_ids"])).fetchone()[0]
    reviews = review_summary(conn, llm, location, start, data_through)
    waiting = [{"creator_id": str(cid), "handle": "@" + h, "sent_at": str(at)[:10]}
               for cid, h, at in conn.execute(
                   "select distinct on (c.id) c.id, c.handle, o.sent_at from outreach o join creators c on c.id = o.creator_id "
                   "where o.campaign_id = any(%s::uuid[]) and o.status = 'sent' order by c.id, o.sent_at",
                   (m["campaign_ids"],))]

    facts = {"location": location, "week_of": str(week_of), "data_through": str(data_through), "metrics": metrics,
             "top_creators": m["top_creators"], "review_summary": reviews, "waiting_for_reply": waiting}

    nothing = not m["campaign_ids"] or (metrics["first_visits"] == 0 and not waiting and not reviews)
    if llm and not nothing:
        allowed = allowed_numbers(facts)
        known = {t["creator_id"] for t in m["top_creators"]} | {w["creator_id"] for w in waiting}

        def check(c: BriefContent) -> list[str]:
            problems = []
            bad = numbers_not_in_facts(c, allowed)
            if bad:
                problems.append(f"these numbers are not in the facts: {bad}")
            unknown = [a.creator_id for a in c.actions if a.creator_id and a.creator_id not in known]
            if unknown:
                problems.append(f"creator_id values not in the facts: {unknown}")
            return problems

        content = llm.structured(system=load_prompt("weekly_brief"), prompt=f"Facts:\n{to_json(facts)}",
                                 output=BriefContent, effort="medium", check=check).model_dump()
    else:
        content = template_content(facts)

    is_sim = bool(metrics.get("simulated_share")) or bool(reviews and reviews["is_simulated"])
    review_out = None if reviews is None else {k: reviews[k] for k in ("positive_share", "is_simulated", "themes")}
    with conn.transaction():
        brief_id = conn.execute(
            "insert into briefs (location, week_of, data_through, metrics, top_creators, review_summary, content, is_simulated) "
            "values (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s) returning id",
            (location, week_of, data_through, to_json(metrics), to_json(m["top_creators"]),
             None if review_out is None else to_json(review_out), to_json(content), is_sim)).fetchone()[0]
        conn.execute("insert into audit_log (actor_id, action, entity, entity_id, meta) "
                     "values (%s, 'brief.generate', 'brief', %s, %s::jsonb)",
                     (actor_id, str(brief_id), to_json({"mode": "llm" if llm else "template", "location": location})))
    return conn.execute("select brief_json(%s)", (brief_id,)).fetchone()[0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("location")
    ap.add_argument("--as-of", type=date.fromisoformat, help="treat this date as today (for simulated data)")
    args = ap.parse_args(argv)
    from .db import connect
    with connect() as conn:
        print(to_json(generate(conn, args.location, as_of=args.as_of)))


if __name__ == "__main__":
    main()
