"""Campaign codes, redemptions, return codes and voids — the rules from Tyler's
spec §3.3/§6 and his 2026-11-18 answers. Times are Sunnyvale (PST, UTC-8)."""

from __future__ import annotations

import json
import re
import threading
import uuid

import psycopg
import pytest

# Campaign: Fri 2026-11-20 .. Fri 2026-12-04, Sunnyvale.
START, END = "2026-11-20", "2026-12-04"


def utc(local: str) -> str:
    """'2026-11-27 18:42' Sunnyvale local -> UTC ISO string."""
    return f"{local}:00-08:00"


def call(conn, fn: str, **kw):
    args = ", ".join(f"p_{k} => %({k})s" for k in kw)
    return conn.execute(f"select {fn}({args})", kw).fetchone()[0]


def fails(conn, fn: str, **kw):
    with pytest.raises(psycopg.Error) as e:
        call(conn, fn, **kw)
    d = e.value.diag
    return {"http": int(e.value.sqlstate[2:]), "code": d.message_primary,
            "details": json.loads(d.message_detail or "{}")}


def make_creators(conn, n: int, platform: str = "instagram") -> list[str]:
    ids = []
    for _ in range(n):
        handle = f"test_{uuid.uuid4().hex[:10]}"
        ids.append(str(conn.execute(
            "insert into creators (handle, platform, source) values (%s, %s, 'TEST') returning id",
            (handle, platform)).fetchone()[0]))
    return ids


def occasion(conn, slug="cold_week") -> str:
    return str(conn.execute("select id from occasions where slug = %s", (slug,)).fetchone()[0])


def new_campaign(conn, creators=None, **overrides):
    creators = creators or make_creators(conn, 1)
    kw = dict(name="First cold week · Sunnyvale", occasion_id=occasion(conn), location="sunnyvale",
              start_date=START, end_date=END, creator_ids=creators, languages=["en", "zh"],
              now=utc("2026-11-18 10:00"))
    kw.update(overrides)
    return call(conn, "create_campaign", **kw), creators


def creator_code(conn, campaign_id: str, creator_id: str) -> str:
    return conn.execute(
        "select code from offer_codes where campaign_id = %s and creator_id = %s and kind = 'creator'",
        (campaign_id, creator_id)).fetchone()[0]


def redeem(conn, code, at, location="sunnyvale", party=2, key=None, **kw):
    return call(conn, "redeem_code", code=code, location=location, party_size=party,
                now=utc(at), idempotency_key=key, **kw)


# --------------------------------------------------------------------- campaigns

def test_create_campaign_makes_codes_and_pending_drafts(conn):
    res, creators = new_campaign(conn, creators=make_creators(conn, 2), languages=["zh", "en", "en"])
    camp = res["campaign"]
    assert camp["status"] == "active" and res["skipped"] == []
    assert camp["generation"] == {"status": "running", "total": 4, "done": 0, "failed": 0}

    rows = conn.execute(
        "select code, iso_utc(starts_at), iso_utc(expires_at), offer, max_uses from offer_codes where campaign_id = %s",
        (camp["id"],)).fetchall()
    assert len(rows) == 2
    for code, starts, expires, offer, max_uses in rows:
        assert re.fullmatch(r"FENG-COLD-[2-9A-HJKMNP-Z]{6}", code)
        assert starts == "2026-11-20T08:00:00Z"            # local midnight
        assert expires == "2026-12-05T07:59:59Z"           # 23:59:59 local on end_date (matches mock)
        assert offer["title"] == {"en": "Free appetizer for your table", "zh": "桌上免费开胃菜"}
        assert max_uses is None

    # Editing the occasion later doesn't change the live offer.
    conn.execute("update occasions set offer_title_en = 'CHANGED' where slug = 'cold_week'")
    try:
        assert conn.execute("select offer->'title'->>'en' from offer_codes where campaign_id = %s limit 1",
                            (camp["id"],)).fetchone()[0] == "Free appetizer for your table"
    finally:
        conn.execute("update occasions set offer_title_en = 'Free appetizer for your table' where slug = 'cold_week'")


def test_create_campaign_idempotency_and_skips(conn):
    key = str(uuid.uuid4())
    first, creators = new_campaign(conn, idempotency_key=key)
    again, _ = new_campaign(conn, creators=creators, idempotency_key=key)
    assert again == first

    # Creator already in an active Sunnyvale campaign -> skipped, not failed.
    other = make_creators(conn, 1)
    res, _ = new_campaign(conn, creators=creators + other)
    assert res["skipped"] == [{"creator_id": creators[0], "reason": "ALREADY_IN_ACTIVE_CAMPAIGN"}]

    # Everyone skipped -> 422 and no campaign row left behind.
    before = conn.execute("select count(*) from campaigns").fetchone()[0]
    err = fails(conn, "create_campaign", name="Dup campaign", occasion_id=occasion(conn), location="sunnyvale",
                start_date=START, end_date=END, creator_ids=creators, languages=["en"], now=utc("2026-11-18 10:00"))
    assert err["code"] == "VALIDATION_FAILED" and err["details"]["skipped"][0]["reason"] == "ALREADY_IN_ACTIVE_CAMPAIGN"
    assert conn.execute("select count(*) from campaigns").fetchone()[0] == before


def test_create_campaign_validation(conn):
    err = fails(conn, "create_campaign", name="x", occasion_id=occasion(conn), location="atlantis",
                start_date=END, end_date=START, creator_ids=[], languages=["fr"], now=utc("2026-11-18 10:00"))
    assert err["http"] == 422 and err["code"] == "VALIDATION_FAILED"
    assert set(err["details"]["fields"]) == {"name", "location", "end_date", "creator_ids", "languages"}


# --------------------------------------------------------------------- redemption

def test_first_visit_issues_return_code_and_return_visit_is_single_use(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)

    assert fails(conn, "redeem_code", code=code, location="sunnyvale", party_size=2, now=utc("2026-11-19 18:00")) == \
        {"http": 422, "code": "CODE_NOT_STARTED", "details": {"starts": "2026-11-20"}}

    # Staff typed it lowercase without hyphens; Fri Nov 27 6:42 PM local.
    first = redeem(conn, code.lower().replace("-", ""), "2026-11-27 18:42", party=6)
    assert first["redemption"]["type"] == "first" and first["redemption"]["visit_number"] == 1
    assert first["redemption"]["redeemed_at"] == "2026-11-28T02:42:00Z"
    ret = first["return_offer"]
    assert re.fullmatch(r"BACK-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}", ret["code"])
    assert ret["starts_at"] == "2026-11-28T08:00:00Z"      # next local day
    assert ret["expires_at"] == "2026-12-28T07:59:59Z"     # day 30, 23:59:59 local (matches mock)
    assert ret["url"] == f"https://creator-loop.example/r/{ret['code']}"
    assert ret["title"] == "Welcome back: free dessert"

    # Can't use the return code on the same visit, or at another location.
    assert fails(conn, "redeem_code", code=ret["code"], location="sunnyvale", party_size=6,
                 now=utc("2026-11-27 19:30"))["code"] == "CODE_NOT_STARTED"
    assert fails(conn, "redeem_code", code=ret["code"], location="philadelphia", party_size=6,
                 now=utc("2026-12-01 19:30")) == \
        {"http": 422, "code": "CODE_WRONG_LOCATION", "details": {"valid_location": "sunnyvale"}}

    back = redeem(conn, ret["code"], "2026-12-01 19:30", party=4)
    assert back["redemption"]["type"] == "return" and back["redemption"]["visit_number"] == 2
    assert back["return_offer"] is None
    assert back["redemption"]["creator_handle"] == first["redemption"]["creator_handle"]

    err = fails(conn, "redeem_code", code=ret["code"], location="sunnyvale", party_size=4, now=utc("2026-12-02 19:00"))
    assert err["code"] == "CODE_ALREADY_USED"
    assert err["details"] == {"used_at": "2026-12-02T03:30:00Z", "location": "sunnyvale"}


def test_creator_code_ends_with_campaign_but_return_code_does_not(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)

    first = redeem(conn, code, "2026-12-04 23:59")            # last minute of the campaign
    assert fails(conn, "redeem_code", code=code, location="sunnyvale", party_size=2,
                 now=utc("2026-12-05 00:00")) == {"http": 422, "code": "CODE_EXPIRED", "details": {"ended": "2026-12-04"}}

    # Return code still works weeks after the campaign ended...
    assert redeem(conn, first["return_offer"]["code"], "2027-01-03 23:59")["redemption"]["type"] == "return"


def test_return_code_expires_after_day_30(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)
    a = redeem(conn, code, "2026-12-01 12:00")["return_offer"]["code"]
    b = redeem(conn, code, "2026-12-01 12:05")["return_offer"]["code"]   # another table, its own code
    assert a != b
    assert redeem(conn, a, "2026-12-31 23:59")["redemption"]["type"] == "return"
    assert fails(conn, "redeem_code", code=b, location="sunnyvale", party_size=2,
                 now=utc("2027-01-01 00:00"))["code"] == "CODE_EXPIRED"


def test_idempotent_redeem_and_party_size_validation(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)
    key = str(uuid.uuid4())
    one = redeem(conn, code, "2026-11-25 19:00", key=key)
    two = redeem(conn, code, "2026-11-25 19:00", key=key)
    assert one == two
    assert conn.execute("select uses from offer_codes where code = %s", (code,)).fetchone()[0] == 1

    for bad in (0, 51):
        assert fails(conn, "redeem_code", code=code, location="sunnyvale", party_size=bad,
                     now=utc("2026-11-25 19:00"))["details"] == {"fields": {"party_size": "Must be between 1 and 50"}}


def test_concurrent_redemption_of_one_return_code(db_url):
    with psycopg.connect(db_url, autocommit=True) as conn:
        res, (cid,) = new_campaign(conn)
        ret = redeem(conn, creator_code(conn, res["campaign"]["id"], cid), "2026-11-25 19:00")["return_offer"]["code"]

    results, barrier = [], threading.Barrier(5)

    def worker():
        with psycopg.connect(db_url, autocommit=True) as c:
            barrier.wait()
            try:
                redeem(c, ret, "2026-11-30 19:00")
                results.append("ok")
            except psycopg.Error as e:
                results.append(e.diag.message_primary)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["CODE_ALREADY_USED"] * 4 + ["ok"]


# --------------------------------------------------------------------- voids

def test_void_rules(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)
    first = redeem(conn, code, "2026-11-27 18:00")
    ret = first["return_offer"]["code"]
    back = redeem(conn, ret, "2026-11-29 18:00")
    rid_first, rid_back = first["redemption"]["id"], back["redemption"]["id"]

    # First visit whose return code was used -> blocked (409).
    err = fails(conn, "void_redemption", redemption_id=rid_first, reason="typo", actor_role="manager",
                now=utc("2026-11-29 18:05"))
    assert err["http"] == 409 and err["code"] == "INVALID_TRANSITION"
    assert err["details"]["reason"] == "RETURN_CODE_USED"

    # Void the return visit -> code usable again; repeating the void is a no-op.
    item = call(conn, "void_redemption", redemption_id=rid_back, reason="Wrong code", actor_role="staff",
                now=utc("2026-11-29 18:05"))
    assert item["voided_reason"] == "Wrong code" and item["voided_at"] == "2026-11-30T02:05:00Z"
    assert call(conn, "void_redemption", redemption_id=rid_back, reason="again", actor_role="staff",
                now=utc("2026-11-29 18:06")) == item
    assert redeem(conn, ret, "2026-12-02 18:00")["redemption"]["type"] == "return"

    assert conn.execute("select count(*) from audit_log where action = 'redemption.void' and entity_id = %s",
                        (rid_back,)).fetchone()[0] == 1


def test_void_first_visit_cancels_unused_return_code(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)
    first = redeem(conn, code, "2026-11-27 18:00", party=3)
    ret = first["return_offer"]["code"]

    item = call(conn, "void_redemption", redemption_id=first["redemption"]["id"], reason="Wrong party size",
                actor_role="staff", now=utc("2026-11-27 18:05"))
    assert item["has_return_offer"] is False
    assert fails(conn, "redeem_code", code=ret, location="sunnyvale", party_size=3,
                 now=utc("2026-11-29 18:00"))["code"] == "CODE_VOIDED"
    assert fails(conn, "public_offer", code=ret)["code"] == "OFFER_UNAVAILABLE"

    # Staff re-enter the visit: a new, different return code.
    again = redeem(conn, code, "2026-11-27 18:06", party=4)
    assert again["return_offer"]["code"] != ret
    assert conn.execute("select uses from offer_codes where code = %s", (code,)).fetchone()[0] == 1


def test_staff_void_window(conn):
    res, (cid,) = new_campaign(conn)
    first = redeem(conn, creator_code(conn, res["campaign"]["id"], cid), "2026-11-27 18:00")
    err = fails(conn, "void_redemption", redemption_id=first["redemption"]["id"], reason="late", actor_role="staff",
                now=utc("2026-11-27 18:16"))
    assert err["code"] == "INVALID_TRANSITION" and err["details"]["can_void_until"] == "2026-11-28T02:15:00Z"
    assert call(conn, "void_redemption", redemption_id=first["redemption"]["id"], reason="late",
                actor_role="manager", now=utc("2026-11-27 18:16"))["voided_reason"] == "late"


# --------------------------------------------------------------------- public offer + attribution

def test_public_offer(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)
    handle = conn.execute("select handle from creators where id = %s", (cid,)).fetchone()[0]

    assert call(conn, "public_offer", code=code, now=utc("2026-11-19 12:00"))["status"] == "not_started"
    page = call(conn, "public_offer", code=code, now=utc("2026-11-25 12:00"))
    assert page == {
        "status": "active",
        "offer": {"title": {"en": "Free appetizer for your table", "zh": "桌上免费开胃菜"},
                  "details": {"en": "One per table · Dine-in", "zh": "每桌限一份 · 仅限堂食"},
                  "kind": "creator", "starts": "2026-11-20", "ends": "2026-12-04"},
        "restaurant": {"name": "Feng Hotpot", "location_name": "Sunnyvale", "address": None},
        "recommended_by": f"@{handle}",
    }
    assert call(conn, "public_offer", code=code, now=utc("2026-12-05 00:00"))["status"] == "expired"

    ret = redeem(conn, code, "2026-11-27 18:42")["return_offer"]["code"]
    rp = call(conn, "public_offer", code=ret, now=utc("2026-11-28 12:00"))
    assert rp["offer"]["kind"] == "return" and rp["offer"]["starts"] == "2026-11-28" and rp["offer"]["ends"] == "2026-12-27"
    assert rp["recommended_by"] is None
    assert fails(conn, "public_offer", code="FENG-NOPE-000000") == \
        {"http": 404, "code": "OFFER_UNAVAILABLE", "details": {}}


def test_attribution_view_excludes_voided(conn):
    res, (cid,) = new_campaign(conn)
    code = creator_code(conn, res["campaign"]["id"], cid)
    a = redeem(conn, code, "2026-11-27 18:00")
    redeem(conn, code, "2026-11-27 18:30", is_simulated=True)
    b = redeem(conn, code, "2026-11-27 19:00")
    redeem(conn, a["return_offer"]["code"], "2026-12-01 18:00")
    call(conn, "void_redemption", redemption_id=b["redemption"]["id"], reason="dupe", actor_role="staff",
         now=utc("2026-11-27 19:01"))

    row = conn.execute(
        "select first_visits, return_visits, first_visits_real, includes_simulated, cost_cents "
        "from campaign_creator_stats where campaign_id = %s", (res["campaign"]["id"],)).fetchone()
    assert row == (2, 1, 1, True, 4500)
