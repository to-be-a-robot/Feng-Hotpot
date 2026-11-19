# Backend guide for the frontend

**For:** Tyler (frontend) · **From:** Shinjini (backend) · **Branch:** `backend`

The backend implements every endpoint in `FRONTEND_SPEC.md` §5.2 and returns the shapes in `mocks/`. Its tests read the mock files and fail if a response is missing a field. This page covers how to call it and the few places where real responses differ from the mocks.

Machine-readable description: [`docs/openapi.json`](openapi.json) (also live at `<API>/openapi.json`; interactive docs at `<API>/docs`).

## 1. Base URL

| Where | URL |
|---|---|
| Local (Shinjini's Mac) | `http://localhost:8000` |
| Deployed | `https://feng-hotpot-api.onrender.com` (or similar; confirmed once deployed) |

Set it as `VITE_API_BASE_URL`. Paths have no `/api` prefix (`GET /creators`), as in spec §5.1.

The deployed server is on a free plan that sleeps when idle. The first request after a quiet period can take about a minute, so show the loading state rather than an error.

## 2. Signing in

Two modes, set on the server (`AUTH_MODE`). Your code only needs to handle the one in use.

**Now: `dev` mode (until D1 is set up).** No sign-in. The server treats every caller as one user. Send:

| Header | Value | Required |
|---|---|---|
| `X-Dev-Key` | shared key (Shinjini sends it privately) | on the deployed server |
| `X-Dev-Role` | `manager`, `staff` or `admin` | optional: switch roles to test screens (default `admin`) |
| `X-Dev-Locations` | e.g. `sunnyvale` | optional |

The dev key will be visible in the browser bundle, which is acceptable only for the hackathon preview and goes away with real sign-in.

**Later: `supabase` mode (D1).** The frontend signs in with Supabase Auth (magic link, or password for the 2–3 backup demo accounts) using `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`, and sends `Authorization: Bearer <access_token>` on every call. The server checks the token with Supabase and reads role and locations from `profiles`. Accounts are created with `python -m feng_workers.users add <email> --role manager --locations sunnyvale [--password ...]`. Add the frontend URLs to Supabase → Authentication → URL Configuration → Redirect URLs.

## 3. Settings: names on each side

| What | Frontend (spec §5.6) | Backend |
|---|---|---|
| API address | `VITE_API_BASE_URL` | – |
| Mock switch | `VITE_USE_MOCKS` | – |
| Site URL for `/r/:code` links and QR codes | `PUBLIC_SITE_URL` | `app_settings.public_base_url` (database setting) |
| CORS allowlist | `ALLOWED_ORIGINS` | `CORS_ORIGINS` (environment variable) |

**Send Shinjini:** the Enter preview URL and the published URL. She adds them to `CORS_ORIGINS` and sets `public_base_url`. Drafts store a placeholder for the offer link, so changing the site URL later doesn't break existing drafts.

## 4. Differences from the mocks

| Where | Mock | Real response | What to do |
|---|---|---|---|
| IDs everywhere | `c_1`, `cmp_1`, `occ_cold_week` | UUIDs | Treat IDs as opaque strings |
| `GET /occasions` items | `id`, `name`, `offer_title`, `offer_details`, `default_cost_cents` | Same, plus `slug`, `name_zh`, `return_offer`, `return_valid_days` | Ignore extras. `POST /campaigns` accepts the UUID `id` or the `slug` as `occasion_id` |
| `GET /campaigns/:id` → `offer.value_cents` | `4500` | `null` | Show "—". Per Aolin (D4), `default_cost_cents` is the cost of getting a creator's post, not the diner offer's value. Cost per creator is in `creators[].cost_cents` |
| `GET /campaigns/:id`, `GET /occasions` → `occasion` | `{id, name}` | `{id, slug, name}` | Ignore `slug` |
| `POST /redemptions` → `return_offer` | `code, url, title, expires_at` | Plus `starts_at` (next local day) | Optional: "Valid from …" |
| `GET /creators` items | as mock | Plus `display_name` | Ignore |
| `GET /briefs/latest` with no brief yet | – | `404 NOT_FOUND` | Show the "Your first brief arrives…" empty state |
| `POST /briefs/generate`, `POST /simulate`, `POST /demo/reset` | – | Admin role and server `DEMO_MODE=true`; otherwise `403` / `404` | Show demo tools only when `GET /me` → `features.demo_tools` |
| `POST /demo/reset` | (P2, no mock) | Body `{"confirm": "RESET"}` → `{"deleted": {...}}` | Confirm in the UI first |

## 5. Errors

Exactly as spec §5.1:

```json
{ "error": { "code": "CODE_EXPIRED", "message": "This offer has ended.", "details": { "ended": "2026-12-04" }, "request_id": "req_1a2b3c4d" } }
```

- `fields` (validation) and `current` (`STALE_VERSION`) are top-level inside `error`, as in the mocks.
- Every response also has an `X-Request-Id` header.
- A malformed or unknown id in the path returns `404 NOT_FOUND`.
- An item at another location also returns `404`, so ids from other locations don't leak.

## 6. Behaviour worth knowing

- **Drafts are written in the background.** `POST /campaigns` returns `201` with `generation.status: "running"`. Poll `GET /campaigns/:id` (`generation`) as spec §4.4 describes. Without an Anthropic key on the server, drafts use plain template text.
- **Double-clicks are safe.** Repeating an outreach action that already happened returns `200` with the current item. Creates and redemptions accept `idempotency_key`.
- **Codes:** `FENG-<OCCASION>-` + 6 characters for creators, `BACK-XXXX-XXXX` for return offers. Input is case-insensitive and ignores spaces and hyphens.
- **Rate limits** (spec §5.5): `/public/offers/:code` 30/min per IP, and after 5 unknown codes in a minute that IP is blocked for 5 minutes (`429` with `retry_after`). `POST /redemptions` 20/min per user. `POST /campaigns` 10/hour per user.
- **Simulated data:** every simulated row has `is_simulated: true`. Campaign detail and list set `is_simulated` when any of their numbers include simulated visits.

## 7. Try it

```bash
# health (no key needed)
curl https://<API>/health

# creators as a manager
curl -H "X-Dev-Key: <key>" -H "X-Dev-Role: manager" "https://<API>/creators?location=sunnyvale"

# redeem as staff
curl -X POST -H "X-Dev-Key: <key>" -H "X-Dev-Role: staff" -H "Content-Type: application/json" \
     -d '{"code": "FENG-COLD-ABC234", "party_size": 2, "idempotency_key": "6f9c1e2a-0000-4000-8000-000000000000"}' \
     https://<API>/redemptions
```

`python -m feng_workers.smoke --base https://<API>` walks the whole loop (campaign → drafts → approve → redeem → simulate → brief) and prints a ✓ or ✗ per step.
