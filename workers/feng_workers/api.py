"""HTTP API implementing Tyler's contract (docs/FRONTEND_SPEC.md §5).

    uvicorn feng_workers.api:app --reload --port 8000

Every endpoint is a thin wrapper around a database function, so if the team
chooses another transport (D6), the same functions can be called from it.
This layer adds: sign-in, role and location checks, rate limits, request ids,
the error body format, and background jobs (draft writing, brief generation).

AUTH_MODE (PENDING D1):
  dev       no sign-in; the user comes from DEV_* env vars (and X-Dev-Role /
            X-Dev-Locations headers, to try staff vs manager). If DEV_ACCESS_KEY
            is set, every signed-in endpoint also needs header X-Dev-Key with
            that value; always set it when the server is reachable online.
  supabase  Authorization: Bearer <Supabase session token>; role and
            locations come from the profiles table.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
import psycopg
from fastapi import BackgroundTasks, Body, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from .config import env

log = logging.getLogger("feng.api")


# =========================================================================== errors

class ApiError(Exception):
    def __init__(self, code: str, http: int, message: str, **extra):
        self.code, self.http, self.message, self.extra = code, http, message, extra


def error_body(request: Request, code: str, message: str, **extra) -> dict:
    return {"error": {"code": code, "message": message, **extra, "request_id": request.state.request_id}}


def db_error_to_response(request: Request, e: psycopg.Error) -> JSONResponse:
    state = e.sqlstate or ""
    if state.startswith("PT") and state[2:].isdigit():
        d = e.diag
        details = json.loads(d.message_detail or "{}")
        extra = {}
        if "fields" in details:
            extra["fields"] = details.pop("fields")
        if "current" in details:
            extra["current"] = details.pop("current")
        if details:
            extra["details"] = details
        return JSONResponse(error_body(request, d.message_primary, d.message_hint or "", **extra),
                            status_code=int(state[2:]))
    log.exception("database error (request %s)", request.state.request_id)
    return JSONResponse(error_body(request, "INTERNAL", "Something went wrong on our side."), status_code=500)


# =========================================================================== rate limits

class RateLimiter:
    """In-memory sliding windows. Fine for one API process; use Redis or the
    database if the API is scaled out."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.blocked: dict[str, float] = {}
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, per: float):
        now = time.monotonic()
        with self.lock:
            until = self.blocked.get(key)
            if until and until > now:
                raise ApiError("RATE_LIMITED", 429, "Too many requests.", retry_after=int(until - now) + 1)
            q = self.hits[key]
            while q and q[0] <= now - per:
                q.popleft()
            if len(q) >= limit:
                raise ApiError("RATE_LIMITED", 429, "Too many requests.", retry_after=int(q[0] + per - now) + 1)
            q.append(now)

    def guess_failed(self, ip: str, limit: int = 5, per: float = 60, block: float = 300):
        """After `limit` invalid codes in `per` seconds, block the IP for `block` seconds."""
        now = time.monotonic()
        with self.lock:
            q = self.hits[f"guess:{ip}"]
            while q and q[0] <= now - per:
                q.popleft()
            q.append(now)
            if len(q) >= limit:
                self.blocked[f"codes:{ip}"] = now + block

    def check_code_block(self, ip: str):
        until = self.blocked.get(f"codes:{ip}")
        if until and until > time.monotonic():
            raise ApiError("RATE_LIMITED", 429, "Too many tries.", retry_after=int(until - time.monotonic()) + 1)


# =========================================================================== auth

@dataclass
class User:
    id: str
    email: str | None
    role: str
    locations: list[str] = field(default_factory=list)
    display_name: str | None = None

    def can_see(self, location: str | None) -> bool:
        return self.role == "admin" or (location is not None and location in self.locations)


class Auth:
    def __init__(self, mode: str, pool: ConnectionPool):
        self.mode = mode
        self.pool = pool
        self.cache: dict[str, tuple[float, User]] = {}

    def __call__(self, request: Request) -> User:
        if self.mode == "dev":
            key = env("DEV_ACCESS_KEY")
            if key and request.headers.get("x-dev-key") != key:
                raise ApiError("UNAUTHENTICATED", 401, "Missing or wrong X-Dev-Key.")
            role = request.headers.get("x-dev-role") or env("DEV_ROLE", "admin")
            locs = request.headers.get("x-dev-locations") or env("DEV_LOCATIONS", "sunnyvale")
            return User(env("DEV_USER_ID", "00000000-0000-4000-8000-000000000001"), "dev@example.com",
                        role, [l.strip() for l in locs.split(",") if l.strip()], "Dev user")
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            raise ApiError("UNAUTHENTICATED", 401, "Please sign in again.")
        token = header[7:]
        cached = self.cache.get(token)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        url, key = env("SUPABASE_URL"), env("SUPABASE_ANON_KEY") or env("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        r = httpx.get(f"{url}/auth/v1/user", headers={"apikey": key, "Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code != 200:
            raise ApiError("UNAUTHENTICATED", 401, "Please sign in again.")
        au = r.json()
        with self.pool.connection() as conn:
            row = conn.execute("select role, locations, display_name from profiles where user_id = %s",
                               (au["id"],)).fetchone()
        if not row:
            raise ApiError("FORBIDDEN", 403, "You don't have access to this.")
        user = User(au["id"], au.get("email"), row[0], list(row[1]), row[2])
        self.cache[token] = (time.monotonic() + 60, user)
        return user


def require(user: User, *roles: str):
    if user.role not in roles and user.role != "admin":
        raise ApiError("FORBIDDEN", 403, "You don't have access to this.")


def pick_location(user: User, location: str | None) -> str | None:
    """Explicit location must be one of the user's; otherwise default to theirs."""
    if location:
        if not user.can_see(location):
            raise ApiError("FORBIDDEN", 403, "You don't have access to this location.")
        return location
    if user.role == "admin" and not user.locations:
        return None
    return user.locations[0] if user.locations else None


# =========================================================================== request bodies

class CampaignIn(BaseModel):
    name: str
    occasion_id: str
    location: str
    start_date: date
    end_date: date
    creator_ids: list[uuid.UUID]
    languages: list[Literal["en", "zh"]] = ["en", "zh"]
    idempotency_key: uuid.UUID | None = None


class OutreachPatch(BaseModel):
    action: Literal["edit", "approve", "reject", "reopen", "mark_sent", "mark_replied", "mark_declined"]
    version: int
    edited_text: str | None = None
    reason: str | None = None


class VersionIn(BaseModel):
    version: int


class RedemptionIn(BaseModel):
    code: str = Field(max_length=64)
    party_size: int
    location: str | None = None
    idempotency_key: uuid.UUID | None = None


class VoidIn(BaseModel):
    reason: str


class SimulateIn(BaseModel):
    campaign_id: uuid.UUID
    days: int = Field(default=14, ge=1, le=60)


class DemoResetIn(BaseModel):
    confirm: str


class BriefGenerateIn(BaseModel):
    location: str
    as_of: date | None = None


# =========================================================================== app

def create_app(database_url: str | None = None, auth_mode: str | None = None) -> FastAPI:
    database_url = database_url or env("DATABASE_URL", required=True)
    auth_mode = (auth_mode or env("AUTH_MODE", "dev")).lower()
    demo_mode = (env("DEMO_MODE", "false") or "").lower() in ("1", "true", "yes")
    pool = ConnectionPool(database_url, min_size=1, max_size=10, kwargs={"autocommit": True}, open=True)
    auth = Auth(auth_mode, pool)
    limiter = RateLimiter()
    if auth_mode == "dev":
        log.warning("AUTH_MODE=dev: no sign-in%s.",
                    " (X-Dev-Key required)" if env("DEV_ACCESS_KEY") else
                    ". Set DEV_ACCESS_KEY before exposing this server online")

    app = FastAPI(title="Feng Hotpot Creator Loop API", version="0.1.0")
    app.state.pool, app.state.limiter = pool, limiter
    origins = [o.strip() for o in (env("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000") or "").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Dev-Role", "X-Dev-Locations", "X-Dev-Key"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = "req_" + uuid.uuid4().hex[:8]
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, e: ApiError):
        return JSONResponse(error_body(request, e.code, e.message, **e.extra), status_code=e.http)

    @app.exception_handler(psycopg.Error)
    async def db_error(request: Request, e: psycopg.Error):
        return db_error_to_response(request, e)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, e: RequestValidationError):
        errs = e.errors()
        if any(err["loc"] and err["loc"][0] == "path" for err in errs):
            return JSONResponse(error_body(request, "NOT_FOUND", "We couldn't find that."), status_code=404)
        fields = {".".join(str(p) for p in err["loc"][1:]) or "body": err["msg"] for err in errs}
        return JSONResponse(error_body(request, "VALIDATION_FAILED", "Check the highlighted fields.", fields=fields),
                            status_code=422)

    def q(sql: str, *params):
        with pool.connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else None

    def location_of(sql: str, entity_id) -> str:
        loc = q(sql, entity_id)
        if loc is None:
            raise ApiError("NOT_FOUND", 404, "We couldn't find that.")
        return loc

    def check_location(user: User, loc: str):
        if not user.can_see(loc):
            # 404, not 403, so other locations' ids don't leak (spec §8.7).
            raise ApiError("NOT_FOUND", 404, "We couldn't find that.")

    def connect():
        return psycopg.connect(database_url, autocommit=True)

    def run_drafts(campaign_id: str):
        from .drafts import run
        try:
            log.info("drafts for %s: %s", campaign_id, run(connect, campaign_id=campaign_id))
        except Exception:
            log.exception("draft generation failed for %s", campaign_id)

    def run_brief(location: str, as_of: date | None, actor: str):
        from .brief import generate
        try:
            with connect() as conn:
                generate(conn, location, as_of=as_of, actor_id=actor)
        except Exception:
            log.exception("brief generation failed for %s", location)

    def demo_only(user: User):
        if not demo_mode:
            raise ApiError("NOT_FOUND", 404, "We couldn't find that.")
        if user.role != "admin":
            raise ApiError("FORBIDDEN", 403, "You don't have access to this.")

    # ------------------------------------------------------------------ session

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/docs")

    @app.get("/health")
    def health():
        return {"ok": q("select 1") == 1}

    @app.get("/me")
    def me(user: User = Depends(auth)):
        return {"user_id": user.id, "email": user.email, "role": user.role, "locations": user.locations,
                "features": {"demo_tools": demo_mode and user.role == "admin"}}

    @app.get("/summary")
    def summary(location: str | None = None, user: User = Depends(auth)):
        require(user, "manager")
        loc = pick_location(user, location)
        if not loc:
            raise ApiError("VALIDATION_FAILED", 422, "Check the highlighted fields.", fields={"location": "Required"})
        return q("select api_summary(%s)", loc)

    # ------------------------------------------------------------------ creators & occasions

    @app.get("/creators")
    def creators(location: str | None = None, platform: list[str] | None = Query(None), min_score: float = 0,
                 q_: str | None = Query(None, alias="q"), sort: str = "score_desc", limit: int = 50,
                 cursor: str | None = None, user: User = Depends(auth)):
        require(user, "manager")
        loc = pick_location(user, location)
        platforms = [p for item in (platform or []) for p in item.split(",") if p]
        return q("select api_creators(%s, %s, %s, %s, %s, %s, %s)", loc, platforms or None, min_score, q_, sort, limit, cursor)

    @app.get("/occasions")
    def occasions(user: User = Depends(auth)):
        require(user, "manager")
        return q("select api_occasions()")

    # ------------------------------------------------------------------ campaigns

    @app.get("/campaigns")
    def campaigns(location: str | None = None, status: str | None = None, limit: int = 50,
                  cursor: str | None = None, user: User = Depends(auth)):
        require(user, "manager")
        return q("select api_campaigns(%s, %s, %s, %s)", pick_location(user, location), status, limit, cursor)

    @app.post("/campaigns", status_code=201)
    def create_campaign(body: CampaignIn, background: BackgroundTasks, user: User = Depends(auth)):
        require(user, "manager")
        limiter.check(f"campaigns:{user.id}", 10, 3600)
        pick_location(user, body.location)
        tz = q("select timezone from locations where slug = %s", body.location)
        fields = {}
        if tz and body.start_date < datetime.now(ZoneInfo(tz)).date():
            fields["start_date"] = "Start today or later"
        if body.end_date > body.start_date + timedelta(days=90):
            fields["end_date"] = "Campaigns can run at most 90 days"
        if fields:
            raise ApiError("VALIDATION_FAILED", 422, "Check the highlighted fields.", fields=fields)
        occasion = q("select id from occasions where id::text = %s or slug = %s", body.occasion_id, body.occasion_id)
        if occasion is None:
            raise ApiError("VALIDATION_FAILED", 422, "Check the highlighted fields.", fields={"occasion_id": "Choose an occasion"})
        result = q("select create_campaign(p_name => %s, p_occasion_id => %s, p_location => %s, p_start_date => %s, "
                   "p_end_date => %s, p_creator_ids => %s::uuid[], p_languages => %s, p_created_by => %s, "
                   "p_idempotency_key => %s)",
                   body.name, occasion, body.location, body.start_date, body.end_date,
                   [str(c) for c in body.creator_ids], list(body.languages), user.id, body.idempotency_key)
        background.add_task(run_drafts, result["campaign"]["id"])
        return result

    @app.get("/campaigns/{campaign_id}")
    def campaign(campaign_id: uuid.UUID, user: User = Depends(auth)):
        require(user, "manager")
        check_location(user, location_of("select location from campaigns where id = %s", campaign_id))
        return q("select api_campaign(%s)", campaign_id)

    @app.patch("/campaigns/{campaign_id}/creators/{cc_id}")
    def update_campaign_creator(campaign_id: uuid.UUID, cc_id: uuid.UUID, body: dict = Body(...),
                                user: User = Depends(auth)):
        require(user, "manager")
        check_location(user, location_of("select location from campaigns where id = %s", campaign_id))
        patch = {k: v for k, v in body.items() if k in ("post_url", "post_date", "cost_cents", "version")}
        return q("select update_campaign_creator(%s, %s, %s, %s)", campaign_id, cc_id, Jsonb(patch), user.id)

    # ------------------------------------------------------------------ outreach

    @app.get("/outreach")
    def outreach(campaign_id: uuid.UUID, status: str | None = None, lang: str | None = None, limit: int = 50,
                 cursor: str | None = None, user: User = Depends(auth)):
        require(user, "manager")
        check_location(user, location_of("select location from campaigns where id = %s", campaign_id))
        return q("select api_outreach(%s, %s, %s, %s, %s)", campaign_id, status, lang, limit, cursor)

    outreach_location = ("select k.location from outreach o join campaigns k on k.id = o.campaign_id "
                         "where o.id = %s")

    @app.patch("/outreach/{outreach_id}")
    def outreach_action(outreach_id: uuid.UUID, body: OutreachPatch, user: User = Depends(auth)):
        require(user, "manager")
        check_location(user, location_of(outreach_location, outreach_id))
        return q("select outreach_action(p_id => %s, p_action => %s, p_version => %s, p_edited_text => %s, "
                 "p_reason => %s, p_actor_id => %s, p_actor_name => %s)",
                 outreach_id, body.action, body.version, body.edited_text, body.reason, user.id,
                 user.display_name or user.email)

    @app.post("/outreach/{outreach_id}/regenerate")
    def regenerate(outreach_id: uuid.UUID, body: VersionIn, background: BackgroundTasks, user: User = Depends(auth)):
        require(user, "manager")
        check_location(user, location_of(outreach_location, outreach_id))
        item = q("select outreach_regenerate(%s, %s, %s)", outreach_id, body.version, user.id)
        background.add_task(run_drafts, item["campaign_id"])
        return item

    # ------------------------------------------------------------------ public offer page

    @app.get("/public/offers/{code}")
    def public_offer(code: str, request: Request):
        ip = request.client.host if request.client else "unknown"
        limiter.check_code_block(ip)
        limiter.check(f"public:{ip}", 30, 60)
        try:
            return q("select public_offer(%s)", code.strip().rstrip("/"))
        except psycopg.Error as e:
            if e.diag.message_primary == "OFFER_UNAVAILABLE":
                limiter.guess_failed(ip)
            raise

    # ------------------------------------------------------------------ redemptions

    redemption_location = "select location from redemptions where id = %s"

    @app.post("/redemptions", status_code=201)
    def redeem(body: RedemptionIn, request: Request, user: User = Depends(auth)):
        require(user, "staff", "manager")
        ip = request.client.host if request.client else "unknown"
        limiter.check_code_block(ip)
        limiter.check(f"redeem:{user.id}", 20, 60)
        # Location comes from the profile; a request for another location is refused.
        loc = pick_location(user, body.location)
        if not loc:
            raise ApiError("VALIDATION_FAILED", 422, "Check the highlighted fields.", fields={"location": "Required"})
        try:
            return q("select redeem_code(p_code => %s, p_location => %s, p_party_size => %s, p_actor_id => %s, "
                     "p_idempotency_key => %s)", body.code, loc, body.party_size, user.id, body.idempotency_key)
        except psycopg.Error as e:
            if e.diag.message_primary == "CODE_INVALID":
                limiter.guess_failed(ip)
            raise

    @app.get("/redemptions/recent")
    def recent(location: str | None = None, limit: int = 10, user: User = Depends(auth)):
        require(user, "staff", "manager")
        loc = pick_location(user, location)
        return q("select recent_redemptions(%s, %s)", loc, limit)

    @app.get("/redemptions/{redemption_id}")
    def redemption(redemption_id: uuid.UUID, user: User = Depends(auth)):
        require(user, "staff", "manager")
        check_location(user, location_of(redemption_location, redemption_id))
        return q("select redemption_response(%s)", redemption_id)

    @app.post("/redemptions/{redemption_id}/void")
    def void(redemption_id: uuid.UUID, body: VoidIn, user: User = Depends(auth)):
        require(user, "staff", "manager")
        check_location(user, location_of(redemption_location, redemption_id))
        return q("select void_redemption(%s, %s, %s, %s)", redemption_id, body.reason, user.id, user.role)

    # ------------------------------------------------------------------ briefs

    @app.get("/briefs/latest")
    def brief_latest(location: str | None = None, user: User = Depends(auth)):
        require(user, "manager")
        return q("select api_brief_latest(%s)", pick_location(user, location))

    @app.get("/briefs")
    def briefs(location: str | None = None, limit: int = 50, cursor: str | None = None, user: User = Depends(auth)):
        require(user, "manager")
        return q("select api_briefs(%s, %s, %s)", pick_location(user, location), limit, cursor)

    @app.post("/briefs/generate", status_code=202)
    def brief_generate(body: BriefGenerateIn, background: BackgroundTasks, user: User = Depends(auth)):
        demo_only(user)
        background.add_task(run_brief, body.location, body.as_of, user.id)
        return {"status": "generating"}

    # ------------------------------------------------------------------ demo tools

    @app.post("/simulate")
    def simulate(body: SimulateIn, background: BackgroundTasks, user: User = Depends(auth)):
        demo_only(user)
        loc = location_of("select location from campaigns where id = %s", body.campaign_id)
        from .simulate import simulate as run_sim
        with connect() as conn:
            result = run_sim(conn, str(body.campaign_id), body.days, actor_id=user.id)
        background.add_task(run_brief, loc, date.fromisoformat(result["as_of"]), user.id)
        return {"campaign_id": result["campaign_id"], "days": result["days"], "added": result["added"],
                "brief": {"status": "generating"}}

    @app.post("/demo/reset")
    def demo_reset(body: DemoResetIn, user: User = Depends(auth)):
        demo_only(user)
        if body.confirm != "RESET":
            raise ApiError("VALIDATION_FAILED", 422, "Check the highlighted fields.",
                           fields={"confirm": 'Send "RESET" to confirm'})
        return q("select demo_reset(%s)", user.id)

    return app


def __getattr__(name):
    # `uvicorn feng_workers.api:app` builds the app on first access, so importing
    # this module (e.g. in tests) doesn't need DATABASE_URL.
    if name == "app":
        logging.basicConfig(level=logging.INFO)
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
