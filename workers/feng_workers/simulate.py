"""Fast-forward a campaign with clearly labeled simulated data.

    python -m feng_workers.simulate <campaign_id> [--days 14]

* Reproducible: the same campaign, seed and days produce the same rows.
* Idempotent: every redemption carries a deterministic idempotency key and
  every review a deterministic id, so running it again adds nothing.
* Goes through redeem_code(), so simulated visits obey the same code rules as
  real ones (dates, single-use return codes, location).
* Everything written has is_simulated = true. Shape: config/simulation.json.
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import load_config

NAMESPACE = uuid.UUID("6f1c2a0e-9b7d-4c1e-8a35-0f6d6c4b2e11")


def _key(*parts) -> str:
    return str(uuid.uuid5(NAMESPACE, ":".join(map(str, parts))))


def _poisson_like(rng: random.Random, rate: float) -> int:
    """Small-count sampler good enough for daily visit counts."""
    trials = max(3, int(rate * 4) + 1)
    return sum(rng.random() < rate / trials for _ in range(trials))


def _weighted(rng: random.Random, weights: dict) -> int:
    keys = list(weights)
    return int(rng.choices(keys, weights=[weights[k] for k in keys])[0])


def simulate(conn, campaign_id: str, days: int = 14, actor_id=None) -> dict:
    cfg = load_config("simulation")
    row = conn.execute(
        "select k.location, k.start_date, k.end_date, l.timezone from campaigns k "
        "join locations l on l.slug = k.location where k.id = %s", (campaign_id,)).fetchone()
    if not row:
        raise LookupError("campaign not found")
    location, start, end, tz_name = row
    tz = ZoneInfo(tz_name)
    days = max(1, min(int(days), 60))
    horizon = start + timedelta(days=days)          # simulated "today"
    rng = random.Random(f"{cfg['seed']}:{campaign_id}:{days}")

    creators = conn.execute(
        """
        select cc.id, c.handle, c.platform, coalesce(c.score, %s), oc.code, cc.post_date
        from campaign_creators cc join creators c on c.id = cc.creator_id
        join offer_codes oc on oc.campaign_creator_id = cc.id and oc.kind = 'creator'
        where cc.campaign_id = %s order by cc.created_at, cc.id
        """, (cfg["unscored_creator_score"], campaign_id)).fetchall()

    def at_dinner(d: date) -> datetime:
        h0, h1 = cfg["dinner_hours_local"]
        local = datetime.combine(d, time(rng.randint(h0, h1 - 1), rng.randint(0, 59)), tzinfo=tz)
        return local.astimezone(ZoneInfo("UTC"))

    before = conn.execute("select count(*) from redemptions where campaign_id = %s", (campaign_id,)).fetchone()[0]
    before_reviews = conn.execute("select count(*) from reviews where location = %s and is_simulated", (location,)).fetchone()[0]

    with conn.transaction():
        for cc_id, handle, platform, score, code, post_date in creators:
            # The creator "posts" a few days in, unless a real post date exists.
            # Always draw, so a re-run consumes the same random sequence.
            simulated_post = start + timedelta(days=rng.randint(*cfg["post_delay_days"]))
            if post_date is None:
                post_date = simulated_post
                conn.execute(
                    "update campaign_creators set post_date = %s, post_url = coalesce(post_url, %s), is_simulated = true "
                    "where id = %s and post_date is null",
                    (post_date, f"https://creators.example/{platform}/{handle}/simulated", cc_id))
            rate = max(cfg["min_first_visit_rate_per_day"],
                       cfg["first_visit_rate_per_day_at_score_100"] * float(score) / 100)
            d = max(start, post_date)
            while d < horizon and d <= end:
                for i in range(_poisson_like(rng, rate)):
                    when = at_dinner(d)
                    party = _weighted(rng, cfg["party_size_weights"])
                    first = conn.execute(
                        "select redeem_code(p_code => %s, p_location => %s, p_party_size => %s, "
                        "p_idempotency_key => %s, p_now => %s, p_is_simulated => true)",
                        (code, location, party, _key(campaign_id, cc_id, d, i), when)).fetchone()[0]
                    ret = first.get("return_offer")
                    if ret and rng.random() < cfg["return_probability"]:
                        back_day = d + timedelta(days=rng.randint(*cfg["return_delay_days"]))
                        if back_day < horizon:
                            conn.execute(
                                "select redeem_code(p_code => %s, p_location => %s, p_party_size => %s, "
                                "p_idempotency_key => %s, p_now => %s, p_is_simulated => true)",
                                (ret["code"], location, party, _key(campaign_id, cc_id, d, i, "return"), at_dinner(back_day)))
                d += timedelta(days=1)

        # Reviews at the location over the same window (Friday waits are part of the story).
        t = cfg["review_templates"]
        d = start
        while d < horizon:
            for i in range(_poisson_like(rng, cfg["reviews_per_day"])):
                roll = rng.random()
                if d.weekday() == 4 and roll < 0.5:
                    sentiment, text, rating = "negative", rng.choice(t["negative_friday"]), 2
                elif roll < 0.7:
                    sentiment, text, rating = "positive", rng.choice(t["positive"]), rng.choice([4, 5])
                elif roll < 0.9:
                    sentiment, text, rating = "neutral", rng.choice(t["neutral"]), 3
                else:
                    sentiment, text, rating = "negative", rng.choice(t["negative"]), 2
                conn.execute(
                    "insert into reviews (id, location, rating, text, sentiment, posted_at, is_simulated, source) "
                    "values (%s, %s, %s, %s, %s, %s, true, 'SIMULATED') on conflict (id) do nothing",
                    (_key("review", campaign_id, d, i), location, rating, text, sentiment, at_dinner(d)))
            d += timedelta(days=1)

        added_r = conn.execute("select count(*) from redemptions where campaign_id = %s", (campaign_id,)).fetchone()[0] - before
        added_v = conn.execute("select count(*) from reviews where location = %s and is_simulated", (location,)).fetchone()[0] - before_reviews
        conn.execute(
            "insert into audit_log (actor_id, action, entity, entity_id, meta) values (%s, 'simulate.run', 'campaign', %s, %s::jsonb)",
            (actor_id, campaign_id, f'{{"days": {days}, "redemptions": {added_r}, "reviews": {added_v}}}'))

    return {"campaign_id": campaign_id, "days": days, "as_of": str(horizon),
            "added": {"redemptions": added_r, "reviews": added_v}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("campaign_id")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args(argv)
    from .db import connect
    with connect() as conn:
        print(simulate(conn, args.campaign_id, args.days))


if __name__ == "__main__":
    main()
