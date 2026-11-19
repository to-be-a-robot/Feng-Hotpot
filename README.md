# Feng Hotpot — Creator-to-Repeat-Visit Loop

Finds local creators, drafts outreach a manager approves, tracks each collaboration from
post → code redemption → repeat visit, and writes a weekly brief.

> Demo data is seeded and synthetic where marked (`is_simulated`, `source`). Nothing sends messages automatically.

## Layout

| Path | What |
|---|---|
| `supabase/migrations/` | Schema, reference data, and the database functions behind every endpoint |
| `supabase/pending/` | Migrations waiting on a team decision (not applied) |
| `workers/feng_workers/` | Python backend: API server, seed loader, embeddings, scoring, draft writer, simulator, weekly brief, evaluation |
| `config/` | Scoring weights, seed CSV mapping, simulation story, hours-saved minutes |
| `prompts/` | Claude prompts (editable without code changes) |
| `docs/FRONTEND_SPEC.md`, `mocks/` | API contract and sample responses (Tyler) |
| `docs/BACKEND_GUIDE.md`, `docs/openapi.json` | How the frontend calls the backend |
| `docs/DEPLOY.md`, `render.yaml`, `Dockerfile` | Putting the API online |
| `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION_DRAFT.md` | Demo run and written submission draft |
| `seed/example/` | Fictional sample CSVs until the real seed arrives |
| `PENDING.md` | Open decisions and where to plug each answer in |

## Try it locally (no Supabase, no API key)

```bash
cd workers
uv venv && uv pip install -e ".[dev]" && source .venv/bin/activate

python -m feng_workers.devdb             # local Postgres; prints a DATABASE_URL line
export DATABASE_URL=...                  # paste the line it printed
python -m feng_workers.load_seed && python -m feng_workers.embed && python -m feng_workers.scoring
uvicorn feng_workers.api:app --port 8000 # leave running; open http://localhost:8000/docs to click through

# in a second terminal (same venv and DATABASE_URL):
python -m feng_workers.smoke             # walks the whole loop and prints ✓ / ✗ per step
```

`python -m feng_workers.devdb --reset` starts over; `--stop` shuts the database down.

## Run the backend

Going online (Supabase + Render, about 45 minutes of clicking): see [docs/DEPLOY.md](docs/DEPLOY.md).
For the frontend side: [docs/BACKEND_GUIDE.md](docs/BACKEND_GUIDE.md).

```bash
cp .env.example .env     # set DATABASE_URL; add ANTHROPIC_API_KEY for real AI text
cd workers
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -e ".[dev]"
source .venv/bin/activate

python -m feng_workers.migrate            # apply new database migrations (tracked; safe to re-run)
python -m feng_workers.load_seed          # creators, posts, brand corpus (--dry-run to validate only)
python -m feng_workers.embed              # caption + brand embeddings
python -m feng_workers.scoring            # 0–100 score, breakdown, one-line reason per creator
uvicorn feng_workers.api:app --reload --port 8000    # the API (docs at /docs)
```

Without `ANTHROPIC_API_KEY`, everything still runs end to end with plain template text
(`AI_MODE=template`); with a key, Claude writes the brand-fit reasons, drafts and brief wording.

Background and one-off jobs:

```bash
python -m feng_workers.drafts --watch               # draft writer (the API also starts it after POST /campaigns)
python -m feng_workers.simulate <campaign_id> --days 14   # demo fast-forward (also POST /simulate)
python -m feng_workers.brief sunnyvale --as-of 2026-12-05 # weekly brief (also POST /briefs/generate)
python -m feng_workers.evaluate --labels seed/labels.csv  # precision@10 + draft acceptance rate
python -m feng_workers.users add <email> --role manager --locations sunnyvale   # sign-in accounts (AUTH_MODE=supabase)
./scripts/tunnel.sh                                  # temporary public URL for the local API
pytest                                               # tests on an embedded Postgres; no Docker, no API key
```

## How it fits together

| Endpoint (spec §5.2) | Database function / worker |
|---|---|
| `GET /me`, `GET /summary` | `profiles`, `api_summary` |
| `GET /creators` | `api_creators` (scores from `scoring.py`) |
| `GET /occasions` | `api_occasions` |
| `GET /campaigns`, `GET /campaigns/:id` | `api_campaigns`, `api_campaign` |
| `POST /campaigns` | `create_campaign` → codes + pending drafts → `drafts.py` in the background |
| `PATCH /campaigns/:id/creators/:ccid` | `update_campaign_creator` |
| `GET /outreach`, `PATCH /outreach/:id`, `POST /outreach/:id/regenerate` | `api_outreach`, `outreach_action`, `outreach_regenerate` |
| `GET /public/offers/:code` | `public_offer` |
| `POST /redemptions`, `GET /redemptions/recent`, `GET /redemptions/:id`, `POST /redemptions/:id/void` | `redeem_code`, `recent_redemptions`, `redemption_response`, `void_redemption` |
| `GET /briefs/latest`, `GET /briefs`, `POST /briefs/generate` | `api_brief_latest`, `api_briefs`, `brief.py` (numbers from `brief_metrics`) |
| `POST /simulate` | `simulate.py` (through `redeem_code`), then `brief.py` |
| `POST /demo/reset` | `demo_reset` |

The API layer (`feng_workers/api.py`) adds sign-in, role and location checks, rate limits,
request ids and the error format. If the team serves the API another way (D6), call the same
database functions from there.

Database errors use SQLSTATE `PT<http status>`: `message` is the error code (e.g. `CODE_EXPIRED`),
`hint` the human message, `details` a JSON string (with `fields` / `current` lifted to the top level by the API).
