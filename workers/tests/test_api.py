"""The HTTP API end to end (AUTH_MODE=dev, AI_MODE=template), checking
response shapes against Tyler's mocks/ and the spec's error format."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from feng_workers import scoring
from feng_workers.api import create_app
from feng_workers.config import REPO_ROOT

from .helpers import make_creators

# Expected fields come straight from Tyler's mocks/ (merged from the frontend branch).
MOCKS = REPO_ROOT / "mocks"


def mock(name):
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


CREATOR_KEYS = set(mock("creators.json")["items"][0])
CAMPAIGN_DETAIL_KEYS = set(mock("campaign_detail.json"))
CC_KEYS = set(mock("campaign_detail.json")["creators"][0])
OUTREACH_KEYS = set(mock("outreach.json")["items"][0])
LIST_ITEM_KEYS = set(mock("campaigns_list.json")["items"][0])
OCCASION_KEYS = set(mock("occasions.json")["items"][0])
RECENT_KEYS = set(mock("redemptions_recent.json")["items"][0])
REDEMPTION_KEYS = set(mock("redemption_first.json")["redemption"])
RETURN_OFFER_KEYS = set(mock("redemption_first.json")["return_offer"])
PUBLIC_OFFER_KEYS = set(mock("public_offer_active.json"))
SUMMARY_KEYS = set(mock("summary.json"))
ME_KEYS = set(mock("me.json"))


@pytest.fixture
def client(db_url, monkeypatch):
    monkeypatch.setenv("AI_MODE", "template")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("DEV_ROLE", "manager")
    monkeypatch.setenv("DEV_LOCATIONS", "sunnyvale")
    app = create_app(database_url=db_url, auth_mode="dev")
    with TestClient(app) as c:
        yield c
    app.state.pool.close()


def err(resp, code, http):
    body = resp.json()
    assert resp.status_code == http, body
    assert body["error"]["code"] == code and body["error"]["request_id"].startswith("req_")
    return body["error"]


def test_full_loop(client, conn):
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    creators = make_creators(conn, 2)
    scoring.score_all(conn)

    me = client.get("/me").json()
    assert ME_KEYS <= set(me)
    assert me["role"] == "manager" and me["locations"] == ["sunnyvale"] and me["features"]["demo_tools"] is False

    occ = client.get("/occasions").json()["items"]
    assert OCCASION_KEYS <= set(occ[0])
    assert [o["slug"] for o in occ][:3] == ["birthday", "group_night", "cold_week"]

    page = client.get("/creators", params={"location": "sunnyvale", "sort": "score_desc", "limit": 100}).json()
    mine = [c for c in page["items"] if c["id"] in creators]
    assert len(mine) == 2 and CREATOR_KEYS <= set(mine[0]) and mine[0]["handle"].startswith("@")
    assert page["total"] >= 2 and len(mine[0]["recent_posts"]) == 3

    # Create campaign -> codes + drafts (background task finishes before the response returns in TestClient).
    key = str(uuid.uuid4())
    body = {"name": "First cold week · Sunnyvale", "occasion_id": "cold_week", "location": "sunnyvale",
            "start_date": str(today), "end_date": str(today + timedelta(days=7)),
            "creator_ids": creators, "languages": ["en", "zh"], "idempotency_key": key}
    r = client.post("/campaigns", json=body)
    assert r.status_code == 201, r.json()
    cid = r.json()["campaign"]["id"]
    assert client.post("/campaigns", json=body).json()["campaign"]["id"] == cid      # idempotent

    detail = client.get(f"/campaigns/{cid}").json()
    assert CAMPAIGN_DETAIL_KEYS <= set(detail) and detail["generation"]["status"] == "done"
    assert CC_KEYS <= set(detail["creators"][0]) and detail["creators"][0]["cost_cents"] == 4500
    assert LIST_ITEM_KEYS <= set(client.get("/campaigns").json()["items"][0])

    items = client.get("/outreach", params={"campaign_id": cid}).json()["items"]
    assert len(items) == 4 and OUTREACH_KEYS <= set(items[0]) and items[0]["has_offer_link"]

    # Approve, double-click, stale version.
    o = items[0]
    approved = client.patch(f"/outreach/{o['id']}", json={"action": "approve", "version": o["version"]})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert client.patch(f"/outreach/{o['id']}", json={"action": "approve", "version": o["version"]}).json() == approved.json()
    stale = err(client.patch(f"/outreach/{o['id']}", json={"action": "mark_sent", "version": o["version"]}),
                "STALE_VERSION", 409)
    assert stale["current"]["id"] == o["id"]

    # Inline edit validation.
    cc = detail["creators"][0]
    bad = err(client.patch(f"/campaigns/{cid}/creators/{cc['campaign_creator_id']}",
                           json={"post_url": "javascript:alert(1)", "version": cc["version"]}), "VALIDATION_FAILED", 422)
    assert "post_url" in bad["fields"]
    ok = client.patch(f"/campaigns/{cid}/creators/{cc['campaign_creator_id']}",
                      json={"post_url": "https://creators.example/p/9", "version": cc["version"]})
    assert ok.status_code == 200 and ok.json()["version"] == cc["version"] + 1

    # Staff redeem: first visit gets a return code; the return code can't be used the same day.
    code = cc["code"]["value"]
    staff = {"X-Dev-Role": "staff"}
    assert client.get("/creators", headers=staff).status_code == 403
    first = client.post("/redemptions", headers=staff,
                        json={"code": code.lower().replace("-", " "), "party_size": 4, "idempotency_key": str(uuid.uuid4())})
    assert first.status_code == 201 and first.json()["redemption"]["type"] == "first"
    assert REDEMPTION_KEYS <= set(first.json()["redemption"]) and RETURN_OFFER_KEYS <= set(first.json()["return_offer"])
    back = first.json()["return_offer"]["code"]
    e = err(client.post("/redemptions", headers=staff, json={"code": back, "party_size": 4}), "CODE_NOT_STARTED", 422)
    assert e["details"]["starts"]
    err(client.post("/redemptions", headers=staff, json={"code": code, "party_size": 0}), "VALIDATION_FAILED", 422)
    recent = client.get("/redemptions/recent", headers=staff).json()
    assert recent["items"][0]["id"] == first.json()["redemption"]["id"] and RECENT_KEYS <= set(recent["items"][0])
    voided = client.post(f"/redemptions/{first.json()['redemption']['id']}/void", headers=staff, json={"reason": "Typo"})
    assert voided.status_code == 200 and voided.json()["voided_reason"] == "Typo"

    # Another location's manager can't see this campaign.
    other = {"X-Dev-Locations": "philadelphia"}
    err(client.get(f"/campaigns/{cid}", headers=other), "NOT_FOUND", 404)
    err(client.post("/redemptions", headers={**staff, **other}, json={"code": code, "party_size": 2, "location": "sunnyvale"}),
        "FORBIDDEN", 403)

    # Public offer page: no auth, generic 404, lockout after repeated bad codes.
    offer = client.get(f"/public/offers/{code.lower()}").json()
    assert PUBLIC_OFFER_KEYS <= set(offer) and offer["status"] == "active" and "score" not in str(offer) and offer["recommended_by"].startswith("@")
    err(client.get("/public/offers/FENG-NOPE-000000"), "OFFER_UNAVAILABLE", 404)
    for _ in range(4):
        client.get("/public/offers/FENG-NOPE-000000")
    err(client.get(f"/public/offers/{code}"), "RATE_LIMITED", 429)

    # Demo tools: hidden from managers, available to admins.
    err(client.post("/simulate", json={"campaign_id": cid, "days": 7}), "FORBIDDEN", 403)
    admin = {"X-Dev-Role": "admin"}
    sim = client.post("/simulate", headers=admin, json={"campaign_id": cid, "days": 7})
    assert sim.status_code == 200 and sim.json()["brief"] == {"status": "generating"}
    latest = client.get("/briefs/latest").json()
    assert latest["location"] == "sunnyvale" and "metrics" in latest and "content" in latest
    summary = client.get("/summary").json()
    assert SUMMARY_KEYS <= set(summary) and summary["location"] == "sunnyvale"


def test_errors_and_ids(client):
    err(client.get("/campaigns/not-a-uuid"), "NOT_FOUND", 404)
    err(client.get(f"/campaigns/{uuid.uuid4()}"), "NOT_FOUND", 404)
    e = err(client.post("/campaigns", json={"name": "x"}), "VALIDATION_FAILED", 422)
    assert "occasion_id" in e["fields"]
    err(client.get("/creators", params={"cursor": "abc"}), "VALIDATION_FAILED", 422)
    assert client.get("/health").json() == {"ok": True}


def test_demo_reset(client):
    admin = {"X-Dev-Role": "admin"}
    err(client.post("/demo/reset", json={"confirm": "RESET"}), "FORBIDDEN", 403)          # managers can't
    err(client.post("/demo/reset", headers=admin, json={"confirm": "yes"}), "VALIDATION_FAILED", 422)
    r = client.post("/demo/reset", headers=admin, json={"confirm": "RESET"})
    assert r.status_code == 200 and "campaigns" in r.json()["deleted"]
    assert client.get("/campaigns", headers=admin).json()["items"] == []
    assert client.get("/occasions").json()["items"]                                       # reference data kept


def test_migrations_are_recorded_once(db_url):
    from feng_workers.migrate import apply, status
    import psycopg
    assert apply(db_url) == []                                                            # nothing pending
    with psycopg.connect(db_url, autocommit=True) as conn:
        done, pending = status(conn)
    assert pending == [] and "20261119000005_demo_reset.sql" in done


def test_dev_access_key(db_url, monkeypatch):
    monkeypatch.setenv("DEV_ACCESS_KEY", "s3cret")
    app = create_app(database_url=db_url, auth_mode="dev")
    with TestClient(app) as c:
        err(c.get("/me"), "UNAUTHENTICATED", 401)
        err(c.get("/me", headers={"X-Dev-Key": "wrong"}), "UNAUTHENTICATED", 401)
        assert c.get("/me", headers={"X-Dev-Key": "s3cret"}).status_code == 200
        assert c.get("/health").status_code == 200                       # public endpoints stay open
        err(c.get("/public/offers/FENG-NOPE-000000"), "OFFER_UNAVAILABLE", 404)
    app.state.pool.close()


def test_supabase_auth_mode(db_url, monkeypatch, conn):
    """Bearer token -> Supabase /auth/v1/user -> profiles row decides role and locations."""
    from feng_workers import api as api_mod
    from feng_workers.users import upsert_profile

    user_id = str(uuid.uuid4())
    upsert_profile(conn, user_id, "staff", ["sunnyvale"], "Front desk")

    class Resp:
        def __init__(self, status, data):
            self.status_code, self._data = status, data

        def json(self):
            return self._data

    def fake_get(url, headers, timeout):
        assert url.endswith("/auth/v1/user")
        token = headers["Authorization"].split()[1]
        return Resp(200, {"id": user_id, "email": "staff@feng.example"}) if token == "good" else Resp(401, {})

    monkeypatch.setattr(api_mod.httpx, "get", fake_get)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    app = create_app(database_url=db_url, auth_mode="supabase")
    with TestClient(app) as c:
        err(c.get("/me"), "UNAUTHENTICATED", 401)
        err(c.get("/me", headers={"Authorization": "Bearer bad"}), "UNAUTHENTICATED", 401)
        me = c.get("/me", headers={"Authorization": "Bearer good"}).json()
        assert me["role"] == "staff" and me["locations"] == ["sunnyvale"]
        err(c.get("/creators", headers={"Authorization": "Bearer good"}), "FORBIDDEN", 403)   # staff only redeem
        err(c.get("/me", headers={"X-Dev-Role": "admin"}), "UNAUTHENTICATED", 401)            # dev headers ignored
    app.state.pool.close()
