"""The HTTP API end to end (AUTH_MODE=dev, AI_MODE=template), checking
response shapes against Tyler's mocks/ and the spec's error format."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from feng_workers import scoring
from feng_workers.api import create_app

from .helpers import make_creators

# Keys from Tyler's mocks (origin/frontend:mocks/*.json).
CREATOR_KEYS = {"id", "handle", "platform", "profile_url", "city", "followers", "score", "score_reason",
                "score_breakdown", "scored_at", "recent_posts", "active_campaigns", "source"}
CAMPAIGN_DETAIL_KEYS = {"id", "name", "occasion", "location", "start_date", "end_date", "status", "offer",
                        "generation", "totals", "creators"}
CC_KEYS = {"campaign_creator_id", "version", "creator", "code", "outreach_summary", "post_url", "post_date",
           "cost_cents", "first_visits", "return_visits", "is_simulated"}
OUTREACH_KEYS = {"id", "version", "campaign_id", "campaign_creator_id", "creator", "platform", "lang", "draft_text",
                 "edited_text", "current_text", "status", "has_offer_link", "referenced_posts", "generation_status",
                 "reject_reason", "approver", "decided_at", "sent_at", "replied_at", "updated_at", "is_simulated"}
LIST_ITEM_KEYS = {"id", "name", "occasion", "location", "start_date", "end_date", "status", "creator_count",
                  "outreach_counts", "first_visits", "return_visits", "generation", "is_simulated"}


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
    assert me["role"] == "manager" and me["locations"] == ["sunnyvale"] and me["features"]["demo_tools"] is False

    occ = client.get("/occasions").json()["items"]
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
    back = first.json()["return_offer"]["code"]
    e = err(client.post("/redemptions", headers=staff, json={"code": back, "party_size": 4}), "CODE_NOT_STARTED", 422)
    assert e["details"]["starts"]
    err(client.post("/redemptions", headers=staff, json={"code": code, "party_size": 0}), "VALIDATION_FAILED", 422)
    recent = client.get("/redemptions/recent", headers=staff).json()
    assert recent["items"][0]["id"] == first.json()["redemption"]["id"]
    voided = client.post(f"/redemptions/{first.json()['redemption']['id']}/void", headers=staff, json={"reason": "Typo"})
    assert voided.status_code == 200 and voided.json()["voided_reason"] == "Typo"

    # Another location's manager can't see this campaign.
    other = {"X-Dev-Locations": "philadelphia"}
    err(client.get(f"/campaigns/{cid}", headers=other), "NOT_FOUND", 404)
    err(client.post("/redemptions", headers={**staff, **other}, json={"code": code, "party_size": 2, "location": "sunnyvale"}),
        "FORBIDDEN", 403)

    # Public offer page: no auth, generic 404, lockout after repeated bad codes.
    offer = client.get(f"/public/offers/{code.lower()}").json()
    assert offer["status"] == "active" and "score" not in str(offer) and offer["recommended_by"].startswith("@")
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
    assert client.get("/summary").json()["location"] == "sunnyvale"


def test_errors_and_ids(client):
    err(client.get("/campaigns/not-a-uuid"), "NOT_FOUND", 404)
    err(client.get(f"/campaigns/{uuid.uuid4()}"), "NOT_FOUND", 404)
    e = err(client.post("/campaigns", json={"name": "x"}), "VALIDATION_FAILED", 422)
    assert "occasion_id" in e["fields"]
    err(client.get("/creators", params={"cursor": "abc"}), "VALIDATION_FAILED", 422)
    assert client.get("/health").json() == {"ok": True}
