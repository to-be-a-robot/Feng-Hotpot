# Pending decisions — where to plug in each answer

The API contract is Tyler's `docs/FRONTEND_SPEC.md` plus `mocks/` (merged into this branch; tests check every response against the mock files).
Everything below runs on a placeholder until answered. Change the listed file, run the
"after" step, and tick the box.

## From Aolin (product and data)

- [ ] **D3 — Return offer and its validity (default 30 days).** Edit the `occasions` rows (`return_offer_*`, `return_valid_days`) in the database or in `supabase/migrations/20261117000002_reference_data.sql`. Already-created campaigns keep their copy.
- [ ] **The five occasions' offers and default costs.** Currently copied from Tyler's `mocks/occasions.json`. Same place as above. Chinese wording needs a native-speaker check.
- [ ] **Seed CSVs: headers, file names, folder.** Edit `config/seed_columns.json` (set optional columns the file lacks to `null`) and `SEED_DIR` in `.env`.
      After: `python -m feng_workers.load_seed --dry-run`, then without `--dry-run`.
- [ ] **Scoring targets.** Weights are set (see Decided); the engagement target rate, posts-per-week target and locality values in `config/scoring.json` are still placeholders.
      After: `python -m feng_workers.scoring`.
- [ ] **Seed CSV extras.** Please include `creator_id` (the same ids as the hand-label sheet, e.g. `c_001`) so labels match creators, and a `bio` column: the scorer uses the bio to catch locality traps like a moved-away creator or 大湾区.
- [ ] **Comment text for comment quality.** The CSVs have counts, not comment text, so `comment_quality` is a stand-in (comments per like). If Aolin can collect a few comments per post, the scorer can ask Claude to rate them instead.
- [ ] **Which cities count as each location's area.** `locations.creator_cities` (set in `supabase/migrations/20261118000004_api_functions.sql`). Used by the Creators location filter and the locality score.
- [ ] **Demo story for the simulator.** `config/simulation.json`: visit rates, return probability, party sizes, review wording (Friday waits are built in).
- [ ] **Disclosure wording in drafts.** `prompts/outreach_draft.md` asks creators to mark posts as gifted or sponsored; confirm the wording with Aolin and Sherry.
- [ ] **Embedding model.** Set `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL` in `.env`.
      After: `python -m feng_workers.embed`, then fill in `supabase/pending/pin_embedding_dimension.sql.template` and move it into `migrations/`.
- [ ] **Fill in the hand labels.** `hand_labels_2026-11-18.csv` has 20 well-chosen creators (including the traps), but the `label` and `reason` columns are empty. Fill `label` with good/bad (or 1/0). Those 20 creators also need to be in the seed CSVs (with the same `creator_id`) so they get scored.
      After: save it as `seed/labels.csv`, then `python -m feng_workers.evaluate --labels seed/labels.csv`.
- [ ] **Restaurant addresses** for the public offer page: `locations.address`.

## From Tyler (frontend and API)

- [ ] **D6 — Who serves the HTTP API.** Tyler's spec (v1.1, Nov 18) now proposes this FastAPI service, called from his `src/lib/api.ts` with a mock switch. **Needs Aolin's OK**, since the plan gave the redemption route to Tyler. Built: `workers/feng_workers/api.py` (FastAPI) implements every §5.2 endpoint except `POST /demo/reset` (P2). If Tyler would rather write routes himself, they call the same database functions, and his routes must:
  - take the location and role from the user's `profiles` row, never from the request body;
  - apply the rate limits (§5.5); the database doesn't;
  - map database errors to the API error body: SQLSTATE `PT<http>`, `message` = code, `hint` = human message, `details` = JSON (lift `fields` and `current` to the top level).
- [ ] **D1 — Sign-in.** Tyler's default: magic link, open sign-ups off, plus 2–3 password demo accounts as a backup. The API runs with `AUTH_MODE=dev` (no sign-in, local only). `AUTH_MODE=supabase` is built for the magic-link default: it checks the Bearer token with Supabase and reads role and locations from `profiles`. Still to do once D1 is confirmed: create the users and `profiles` rows, and add RLS policies (RLS is on with no policies, so the browser key can't touch tables).
- [ ] **`offer.value_cents` in `GET /campaigns/:id` is now null.** Per Aolin's D4, the occasion's default cost is the creator cost (comped meal + fee), not the diner offer's value, so it's no longer shown as the offer value. Cost per creator stays in `creators[].cost_cents`. His mock shows 4500 there; the UI should show "—" for null.
- [ ] **Frontend URL** (known after Tyler's first Enter publish, likely `*.enter.pro`). Set `CORS_ORIGINS` in `.env` (Enter preview URL, published URL, `http://localhost:5173`) and `app_settings.public_base_url` (for `/r/:code` links; currently `https://creator-loop.example`). Drafts store `{{offer_link}}` and render the link on read, so changing the URL later doesn't break them. Spec §5.6 calls these settings `ALLOWED_ORIGINS` and `PUBLIC_SITE_URL`; tell Tyler the backend's names.
- [ ] **Brief has no `/briefs/latest` yet → 404 `NOT_FOUND`.** Confirm that's how he wants "no brief yet" signalled (the UI shows its empty state).

## Whole team

- [ ] **Creator model:** one row per platform account (current) or one person with several accounts. Aolin's label sheet merges one person's TikTok and Instagram into one row (c_006), which leans toward one person per row; that would change the `creators` table and the seed format.
- [ ] **Hours saved:** the per-action minutes in `config/brief.json` (currently 20 min research per creator, 10 per message, 1 per redemption logged).
- [ ] **Review attribution:** reviews stay unlinked to campaigns unless agreed.

## Decided

- 2026-11-18 (Tyler, spec update): **creator codes are `FENG-<OCCASION>-` + 6 characters** and **return offers start the next local day**; the mocks now match the backend.
- 2026-11-18 (Aolin): **D4 cost** = what Feng Hotpot spends to get one creator's post (comped meal + any fee), excluding the offers diners redeem. Stored per creator in `campaign_creators.cost_cents`, defaulting to the occasion's `default_cost_cents`. Cost per first visit = sum of creator costs ÷ first visits.
- 2026-11-18 (Aolin): **D5** — one location per campaign; codes only work at the campaign's location.
- 2026-11-18 (Aolin): **Scoring weights** — locality 0.25, brand fit 0.20, comment quality 0.15, engagement 0.15, niche 0.15, cadence 0.10 (`config/scoring.json`).

- 2026-11-18 (Tyler): **Return codes.** One per first-visit redemption, regardless of party size. Valid from the next local day through day `return_valid_days`, until 23:59:59 local. Same location only. Not affected by the campaign end date. No extension after expiry.
- 2026-11-18 (Tyler): **Voids.**
  - First visit, return code unused: the return code is voided (`CODE_VOIDED`).
  - First visit, return code used: blocked with `409 INVALID_TRANSITION`.
  - Return visit: the return code becomes usable again.
  - Staff can void within 15 minutes; managers at any time. Every void is audit-logged.
- 2026-11-18 (Tyler): **Occasions** live in a database table with a unique `slug` and an `is_active` flag (never deleted while in use). The offer is copied onto each campaign and code at creation.
- **Repeat visits** = return-code redemptions. Repeat rate = return visits ÷ first visits, counted per party. No diner personal data.
- **Response rate** = (replied + declined) ÷ (sent + replied + declined), per spec §5.4.
- **D8:** max 25 creators per campaign (`app_settings.max_creators_per_campaign`).
- Posts need a `url`; the loader uses it to de-duplicate.
- **AI text without a key:** `AI_MODE=template` writes plain placeholder text so the whole loop runs without `ANTHROPIC_API_KEY`. With a key it switches to Claude (`claude-opus-5-5`) with server-side refusal fallback on (`LLM_FALLBACKS=default`).
