"""Walk the whole loop against a running API and report each step.

    python -m feng_workers.smoke                       # API at http://localhost:8000
    python -m feng_workers.smoke --base https://...    # a deployed API

Needs AUTH_MODE=dev and DEMO_MODE=true on the server (it switches between the
manager, staff and admin roles with the X-Dev-Role header). It creates a real
campaign and redemptions in whatever database the API uses — don't point it
at production data.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import date, timedelta

import httpx

OK, FAIL = "✓", "✗"


class Smoke:
    def __init__(self, base: str, location: str, dev_key: str | None = None):
        self.http = httpx.Client(base_url=base.rstrip("/"), timeout=120,
                                 headers={"X-Dev-Key": dev_key} if dev_key else {})
        self.loc = location
        self.failed = False

    def call(self, method, path, role="manager", **kw):
        headers = {"X-Dev-Role": role, "X-Dev-Locations": self.loc}
        return self.http.request(method, path, headers=headers, **kw)

    def step(self, label, fn):
        try:
            detail = fn()
            print(f"  {OK} {label}" + (f": {detail}" if detail else ""))
            return True
        except Exception as e:
            self.failed = True
            print(f"  {FAIL} {label}: {e}")
            return False


def expect(resp, status=200):
    if resp.status_code != status:
        raise AssertionError(f"HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


def run(base: str, location: str, dev_key: str | None = None) -> bool:
    s = Smoke(base, location, dev_key)
    ctx: dict = {}
    print(f"Smoke test against {base} ({location})\n")

    s.step("API is up", lambda: expect(s.http.get("/health")) and None)
    s.step("Signed in (dev mode)", lambda: expect(s.call("GET", "/me"))["role"])
    s.step("Occasions", lambda: ", ".join(o["name"] for o in expect(s.call("GET", "/occasions"))["items"]))

    def creators():
        page = expect(s.call("GET", "/creators", params={"location": location, "limit": 100}))
        if not page["items"]:
            raise AssertionError("no creators — run load_seed, embed and scoring first")
        ctx["free"] = [c["id"] for c in page["items"] if not c["active_campaigns"]][:3]
        top = page["items"][0]
        return f"{page['total']} found; top {top['handle']} score {top['score']}: {top['score_reason']}"
    if not s.step("Creators are scored", creators):
        return False

    def campaign():
        if ctx["free"]:
            today = date.today()
            r = expect(s.call("POST", "/campaigns", json={
                "name": "Smoke test · first cold week", "occasion_id": "cold_week", "location": location,
                "start_date": str(today), "end_date": str(today + timedelta(days=14)),
                "creator_ids": ctx["free"], "languages": ["en", "zh"], "idempotency_key": str(uuid.uuid4())}), 201)
            ctx["campaign"] = r["campaign"]["id"]
            return f"created with {len(ctx['free'])} creators"
        items = expect(s.call("GET", "/campaigns", params={"status": "active"}))["items"]
        if not items:
            raise AssertionError("every creator is already in a campaign; try `python -m feng_workers.devdb --reset`")
        ctx["campaign"] = items[0]["id"]
        return f"reusing active campaign '{items[0]['name']}' (all creators are already in one)"
    if not s.step("Campaign + offer codes", campaign):
        return False

    def drafts():
        for _ in range(60):
            gen = expect(s.call("GET", f"/campaigns/{ctx['campaign']}"))["generation"]
            if gen["status"] in ("done", "partial", "failed"):
                break
            time.sleep(2)
        items = expect(s.call("GET", "/outreach", params={"campaign_id": ctx["campaign"]}))["items"]
        ready = [o for o in items if o["generation_status"] == "ready"]
        if not ready:
            raise AssertionError(f"no drafts ready (generation: {gen})")
        ctx["draft"] = next((o for o in ready if o["status"] == "draft"), None)
        sample = ready[0]["current_text"].replace("\n", " ")
        return f"{len(ready)}/{len(items)} ready ({gen['status']}). e.g. [{ready[0]['lang']}] {sample[:110]}…"
    s.step("Drafts written", drafts)

    def approve():
        o = ctx.get("draft")
        if not o:
            return "nothing in draft status (already approved)"
        r = expect(s.call("PATCH", f"/outreach/{o['id']}", json={"action": "approve", "version": o["version"]}))
        return f"{r['status']} (offer link included: {r['has_offer_link']})"
    s.step("Manager approves a draft", approve)

    def redeem():
        detail = expect(s.call("GET", f"/campaigns/{ctx['campaign']}"))
        code = detail["creators"][0]["code"]["value"]
        r = expect(s.call("POST", "/redemptions", role="staff",
                          json={"code": code.lower(), "party_size": 4, "idempotency_key": str(uuid.uuid4())}), 201)
        ctx["code"] = code
        ret = r["return_offer"]
        return f"{code} → first visit by {r['redemption']['creator_handle']}; return code {ret['code']} until {ret['expires_at']}"
    s.step("Staff redeem a creator code", redeem)

    s.step("Public offer page", lambda: (lambda o: f"{o['status']}: {o['offer']['title']['en']} / {o['offer']['title']['zh']}")(
        expect(s.call("GET", f"/public/offers/{ctx['code']}"))) if ctx.get("code") else "skipped")

    def simulate():
        r = expect(s.call("POST", "/simulate", role="admin", json={"campaign_id": ctx["campaign"], "days": 14}))
        return f"added {r['added']['redemptions']} simulated visits and {r['added']['reviews']} reviews"
    s.step("Fast-forward 14 days (simulated)", simulate)

    def brief():
        for _ in range(45):
            r = s.call("GET", "/briefs/latest")
            if r.status_code == 200:
                b = r.json()
                m = b["metrics"]
                actions = "; ".join(a["title"] for a in b["content"]["actions"])
                return (f"week of {b['week_of']}: {m['first_visits']} first / {m['return_visits']} return visits, "
                        f"repeat rate {m['repeat_visit_rate']}. Headline: {b['content']['headline']} Actions: {actions}")
            time.sleep(2)
        raise AssertionError("no brief after 90 s (check the API log)")
    s.step("Weekly brief", brief)

    print("\n" + ("Some steps failed." if s.failed else "Everything works end to end."))
    return not s.failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--location", default="sunnyvale")
    ap.add_argument("--dev-key", default=None, help="X-Dev-Key, if the server sets DEV_ACCESS_KEY "
                                                   "(defaults to DEV_ACCESS_KEY from .env)")
    args = ap.parse_args(argv)
    from .config import env
    sys.exit(0 if run(args.base, args.location, args.dev_key or env("DEV_ACCESS_KEY")) else 1)


if __name__ == "__main__":
    main()
