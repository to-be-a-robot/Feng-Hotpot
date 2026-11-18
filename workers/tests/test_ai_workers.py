"""Claude helper, scoring, drafts, outreach actions, simulator, brief, eval —
all without network: Claude is replaced by FakeClient."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import psycopg
import pytest
from pydantic import BaseModel, Field

from feng_workers import brief, drafts, evaluate, scoring, simulate
from feng_workers.llm import LLMError, LLMRefusal, api_schema

from .helpers import fake_llm, make_creators


@pytest.fixture
def connect(db_url):
    return lambda: psycopg.connect(db_url, autocommit=True)


def campaign(conn, creators, location="sunnyvale", start="2026-11-20", end="2026-12-04", langs=("en", "zh")):
    occ = conn.execute("select id from occasions where slug = 'cold_week'").fetchone()[0]
    return conn.execute(
        "select create_campaign(p_name => 'Test campaign', p_occasion_id => %s, p_location => %s, "
        "p_start_date => %s, p_end_date => %s, p_creator_ids => %s::uuid[], p_languages => %s, "
        "p_now => '2026-11-18T12:00:00Z')", (occ, location, start, end, creators, list(langs))).fetchone()[0]["campaign"]["id"]


# --------------------------------------------------------------------- LLM helper

class Nested(BaseModel):
    label: str = Field(max_length=10)


class Out(BaseModel):
    score: int = Field(ge=0, le=10)
    items: list[Nested]


def test_api_schema_is_closed_and_self_contained():
    s = api_schema(Out)
    assert s["additionalProperties"] is False and s["required"] == ["score", "items"]
    item = s["properties"]["items"]["items"]
    assert item["additionalProperties"] is False and "$ref" not in str(s)
    assert "maximum" not in str(s) and "maxLength" not in str(s)   # enforced locally instead


def test_structured_retries_with_feedback_then_succeeds():
    replies = iter([{"score": 42, "items": []}, {"score": 7, "items": [{"label": "bad"}]}, {"score": 7, "items": [{"label": "ok"}]}])
    llm, client = fake_llm(lambda kw, n: next(replies))
    out = llm.structured(system="s", prompt="p", output=Out,
                         check=lambda o: ["label 'bad' not allowed"] if o.items and o.items[0].label == "bad" else [])
    assert out.score == 7 and len(client.calls) == 3
    assert "score" in client.calls[1]["messages"][-1]["content"]           # validation feedback
    assert "not allowed" in client.calls[2]["messages"][-1]["content"]     # check feedback
    assert client.calls[0]["fallbacks"] == "default"
    assert client.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_structured_gives_up_and_refusal_raises():
    llm, _ = fake_llm(lambda kw, n: {"score": 99, "items": []})
    with pytest.raises(LLMError):
        llm.structured(system="s", prompt="p", output=Out)
    llm, _ = fake_llm(lambda kw, n: SimpleNamespace(stop_reason="refusal", stop_details=None, content=[]))
    with pytest.raises(LLMRefusal):
        llm.structured(system="s", prompt="p", output=Out)


# --------------------------------------------------------------------- scoring

def test_scoring_template_and_llm(conn, monkeypatch):
    ids = make_creators(conn, 3)
    monkeypatch.setenv("AI_MODE", "template")
    result = scoring.score_all(conn)
    assert result["mode"] == "template" and result["scored"] >= 3
    for cid in ids:
        score, breakdown, reason = conn.execute(
            "select score, score_breakdown, score_reason from creators where id = %s", (cid,)).fetchone()
        assert 0 <= score <= 100 and reason
        assert set(breakdown) == set(scoring.FEATURES) and breakdown["brand_fit"] is None
        assert breakdown["locality"] >= 0.75     # Sunnyvale creator + local keywords

    monkeypatch.setenv("AI_MODE", "llm")
    llm, client = fake_llm(lambda kw, n: {"fit_0_10": 8, "reason": "Group hotpot nights in Sunnyvale; real conversations."})
    scoring.score_all(conn, llm)
    b, reason = conn.execute("select score_breakdown, score_reason from creators where id = %s", (ids[0],)).fetchone()
    assert b["brand_fit"] == 0.8 and reason.startswith("Group hotpot")
    assert "<caption>" in client.calls[0]["messages"][0]["content"]       # captions wrapped as untrusted


def test_locality_traps():
    cfg = scoring.load_config("scoring")
    locs = [{"slug": "sunnyvale", "name": "Sunnyvale", "cities": ["sunnyvale", "san jose", "bay area"]}]
    post = lambda text: {"caption": text, "posted_at": None, "likes": None, "comments": None}
    local = scoring.CreatorData("1", "a", "xiaohongshu", "Bay Area", 100, posts=[post("湾区火锅探店")])
    gba = scoring.CreatorData("2", "b", "xiaohongshu", None, 100, posts=[post("大湾区逛吃 湾区美食")], bio="大湾区Kenny")
    moved = scoring.CreatorData("3", "c", "instagram", "Bay Area", 100, posts=[post("bay area eats")], bio="#tiffanyseatssd for San Diego recs")
    assert scoring.locality(local, locs, cfg) > 0.6
    assert scoring.locality(gba, locs, cfg) <= cfg["locality"]["outside_area"]
    assert scoring.locality(moved, locs, cfg) <= cfg["locality"]["outside_area"]


def test_combine_skips_unknown_features():
    w = {"a": 0.5, "b": 0.5}
    assert scoring.combine({"a": 1.0, "b": None}, w) == 100
    assert scoring.combine({"a": None, "b": None}, w) is None


# --------------------------------------------------------------------- drafts + outreach actions

def test_drafts_llm_path_cleans_links_and_ids(conn, connect, monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    creators = make_creators(conn, 1)
    cid = campaign(conn, creators, langs=("en",))
    post_ids = [str(r[0]) for r in conn.execute("select id from creator_posts where creator_id = %s", (creators[0],))]

    def respond(kw, n):
        if n == 1:   # invalid post id -> check feedback
            return {"message": "Hi! Loved your hotpot night post, come visit us.", "referenced_post_ids": ["nope"]}
        return {"message": "Hi! Loved your hotpot night post. See https://evil.example/x and come visit us!",
                "referenced_post_ids": [post_ids[0]]}

    llm, client = fake_llm(respond)
    assert drafts.run(connect, campaign_id=cid, concurrency=1, llm=llm)["processed"] == 1
    text, refs, status, link = conn.execute(
        "select draft_text, referenced_post_ids, generation_status, has_offer_link from outreach where campaign_id = %s",
        (cid,)).fetchone()
    code = conn.execute("select code from offer_codes where campaign_id = %s and kind = 'creator'", (cid,)).fetchone()[0]
    assert status == "ready" and link and "evil.example" not in text
    assert text.count(f"/r/{code}") == 1 and [str(r) for r in refs] == [post_ids[0]]
    assert '<post id="' in client.calls[0]["messages"][0]["content"]


def test_draft_failure_is_recorded(conn, connect, monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    cid = campaign(conn, make_creators(conn, 1), langs=("zh",))

    def boom(kw, n):
        raise RuntimeError("API down")

    llm, _ = fake_llm(boom)
    drafts.run(connect, campaign_id=cid, concurrency=1, llm=llm)
    assert conn.execute("select generation_status, generation_error from outreach where campaign_id = %s",
                        (cid,)).fetchone() == ("failed", "API down")


def test_outreach_actions_and_acceptance_eval(conn, connect, monkeypatch):
    monkeypatch.setenv("AI_MODE", "template")
    cid = campaign(conn, make_creators(conn, 1))
    drafts.run(connect, campaign_id=cid, concurrency=2)
    rows = conn.execute("select id, version from outreach where campaign_id = %s order by lang", (cid,)).fetchall()
    (en_id, en_v), (zh_id, zh_v) = rows

    def act(oid, action, version, **kw):
        args = ", ".join(f"p_{k} => %({k})s" for k in kw)
        return conn.execute(f"select outreach_action(p_id => %(id)s, p_action => %(a)s, p_version => %(v)s"
                            f"{', ' + args if args else ''}, p_actor_name => 'Manager')",
                            {"id": oid, "a": action, "v": version, **kw}).fetchone()[0]

    approved = act(en_id, "approve", en_v)
    assert approved["status"] == "approved" and approved["approver"] == "Manager" and approved["has_offer_link"]
    assert act(en_id, "approve", en_v) == approved                      # double-click, stale version: same item

    with pytest.raises(psycopg.Error) as e:                              # stale version on a real change
        act(en_id, "mark_sent", en_v)
    assert e.value.diag.message_primary == "STALE_VERSION" and e.value.sqlstate == "PT409"

    with pytest.raises(psycopg.Error) as e:                              # not allowed from approved
        act(en_id, "mark_replied", approved["version"])
    assert e.value.diag.message_primary == "INVALID_TRANSITION"

    edited = act(en_id, "edit", approved["version"], edited_text="New text without the link")
    assert edited["status"] == "draft" and edited["approver"] is None and edited["has_offer_link"] is False
    re_approved = act(en_id, "approve", edited["version"])
    sent = act(en_id, "mark_sent", re_approved["version"])
    assert sent["status"] == "sent" and sent["sent_at"]
    replied = act(en_id, "mark_replied", sent["version"])
    assert replied["status"] == "replied" and replied["replied_at"]
    act(zh_id, "reject", conn.execute("select version from outreach where id = %s", (zh_id,)).fetchone()[0],
        reason="Too formal")

    ev = evaluate.draft_eval(conn)
    assert ev["approved"] >= 1 and ev["rejected"] >= 1 and 0 < ev["acceptance_rate"] < 1


# --------------------------------------------------------------------- simulator + brief

def test_simulate_is_idempotent_and_feeds_the_brief(conn, monkeypatch):
    monkeypatch.setenv("AI_MODE", "template")
    cid = campaign(conn, make_creators(conn, 3, city="Rockville"), location="rockville")
    first = simulate.simulate(conn, cid, 14)
    assert first["added"]["redemptions"] > 0 and first["added"]["reviews"] > 0
    again = simulate.simulate(conn, cid, 14)
    assert again["added"] == {"redemptions": 0, "reviews": 0}
    assert conn.execute("select bool_and(is_simulated) from redemptions where campaign_id = %s", (cid,)).fetchone()[0]

    b = brief.generate(conn, "rockville", as_of=date.fromisoformat(first["as_of"]))
    m = b["metrics"]
    firsts = conn.execute("select count(*) from redemptions where campaign_id = %s and type = 'first' and voided_at is null "
                          "and (redeemed_at at time zone 'America/New_York')::date <= %s",
                          (cid, b["data_through"])).fetchone()[0]
    assert m["first_visits"] == firsts and m["simulated_share"] == 1 and b["is_simulated"]
    assert m["hours_saved_estimate"] > 0 and b["content"]["headline"]
    assert b["review_summary"]["is_simulated"] is True


def test_brief_llm_rejects_invented_numbers(conn, monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")
    cid = campaign(conn, make_creators(conn, 2, city="Philadelphia"), location="philadelphia")
    sim = simulate.simulate(conn, cid, 14)
    top = conn.execute("select brief_metrics('philadelphia', %s, %s)",
                       (date(2026, 11, 30), date(2026, 12, 3))).fetchone()[0]["top_creators"]

    def respond(kw, n):
        if "<review id=" in kw["messages"][0]["content"]:
            ids = re.findall(r'<review id="([^"]+)"', kw["messages"][0]["content"])
            return {"themes": [{"label": "Friday wait time", "review_ids": ids[:2]}]}
        action = {"title": "Rebook top creator", "detail": "They drove the most visits.",
                  "creator_id": top[0]["creator_id"] if top else None}
        if n == 2:   # first brief attempt invents a number
            return {"headline": "Visits grew 999% this week.", "highlights": ["Busy week."], "review_signals": [],
                    "actions": [action] * 3}
        return {"headline": "Creators are bringing guests in.", "highlights": ["Return codes are working."],
                "review_signals": [], "actions": [action] * 3}

    llm, client = fake_llm(respond)
    b = brief.generate(conn, "philadelphia", as_of=date.fromisoformat(sim["as_of"]), llm=llm)
    assert b["content"]["headline"] == "Creators are bringing guests in."
    assert "999" in client.calls[-1]["messages"][-1]["content"]          # feedback named the bad number
    assert b["review_summary"]["themes"][0] == {"label": "Friday wait time", "count": 2}


def test_ranking_eval(conn, tmp_path):
    ids = make_creators(conn, 2)
    handles = [conn.execute("select handle from creators where id = %s", (i,)).fetchone()[0] for i in ids]
    conn.execute("update creators set score = 99 where id = %s", (ids[0],))
    conn.execute("update creators set score = 98 where id = %s", (ids[1],))
    conn.execute("update creators set external_id = 'c_901' where id = %s", (ids[0],))
    labels = tmp_path / "labels.csv"
    labels.write_text("creator_id,handle,platform,label,reason\n"
                      f"c_901,Display Name (ID 123),instagram,good,local\n"     # matched by creator_id
                      f",{handles[1]},IG,0,\n"                                 # matched by platform + handle
                      "c_902,@someone,tiktok,,\n")                             # blank label: skipped
    found, unlabeled = evaluate.read_labels(labels)
    assert len(found) == 2 and unlabeled == ["id:c_902 (@someone)"]
    r = evaluate.ranking_eval(conn, found, k=2, unlabeled=unlabeled)
    assert r["precision_at_k"] == 0.5 and r["top_k"][0]["label_good"] is True
    assert r["top_k"][0]["label_key"] == "id:c_901"
