# Putting the backend online

About 45 minutes, mostly waiting and clicking. You need a Supabase account and a Render account (both free; sign in with GitHub). Everything in the repo is already prepared.

## Part 1: Supabase database (about 15 minutes)

1. Go to **supabase.com** → **New project**. Name it `feng-hotpot` and pick the region closest to you (e.g. West US). Set a database password and **save it in your password manager**: you can't see it again.
2. Wait about 2 minutes until the project is ready.
3. Click **Connect** (top of the project page) → **Connection string** → choose **Session pooler** → copy the URI.
   - It looks like `postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-us-west-1.pooler.supabase.com:5432/postgres`.
   - Replace `[YOUR-PASSWORD]` with the password from step 1.
   - Use the pooler, not "Direct connection": the direct address is IPv6-only and Render can't reach it.
4. In `.env` on your Mac, set `DATABASE_URL=` to that URI (replacing the local one; keep the local one in a comment if you want to switch back).
5. In the terminal:
   ```bash
   cd "/Users/shinjinihalder/Feng Hotpot Hackathon/Feng-Hotpot/workers"
   source .venv/bin/activate
   python -m feng_workers.migrate        # creates all tables and functions (prints the 5 files)
   python -m feng_workers.load_seed      # example data for now; Aolin's real CSVs later
   python -m feng_workers.embed
   python -m feng_workers.scoring
   ```
6. Check in Supabase → **Table Editor**: `creators`, `occasions` and `locations` have rows.
7. Still in Supabase → **Project Settings** → **API**, note for later:
   - **Project URL** (`https://abcdefgh.supabase.co`)
   - the **anon / publishable** key (safe for the browser; Tyler needs it for sign-in later)
   - the **service_role / secret** key: admin access, **only** for your `.env`, never for Tyler or the frontend.

## Part 2: The API on Render (about 20 minutes)

1. Go to **render.com** → sign in with GitHub → allow access to `to-be-a-robot/Feng-Hotpot`.
2. **New** → **Blueprint** → pick the `Feng-Hotpot` repo and the **`backend`** branch. Render reads `render.yaml` and shows one service, `feng-hotpot-api`.
3. Fill in the values it asks for:

   | Setting | Value |
   |---|---|
   | `DATABASE_URL` | the Session pooler URI from Part 1 (with your password) |
   | `ANTHROPIC_API_KEY` | your Claude key, or leave empty for template text |
   | `CORS_ORIGINS` | Tyler's Enter preview and published URLs, comma-separated (add `http://localhost:5173` too) |
   | `CORS_ORIGIN_REGEX` | leave empty, or `https://.*\.enter\.pro` if his preview URL keeps changing |
   | `SUPABASE_URL`, `SUPABASE_ANON_KEY` | from Part 1 step 7 (only needed once sign-in is switched on) |

   `DEV_ACCESS_KEY` is generated for you.
4. Click **Apply** and wait for the first deploy (about 5 minutes). The log ends with `Uvicorn running on http://0.0.0.0:...`.
5. Your API address is shown at the top, e.g. `https://feng-hotpot-api.onrender.com`. Open `https://<that>/health` → `{"ok":true}`.
6. Find the generated key: service → **Environment** → `DEV_ACCESS_KEY` → reveal.
7. Run the full check from your Mac:
   ```bash
   python -m feng_workers.smoke --base https://feng-hotpot-api.onrender.com --dev-key <DEV_ACCESS_KEY>
   ```
   Every step should show ✓.
8. Send Tyler the API address and the `DEV_ACCESS_KEY` (privately), and point him to `docs/BACKEND_GUIDE.md`.

**Good to know about the free plan:** the server sleeps after about 15 minutes without requests, and the next request takes about a minute to wake it. Open the app a few minutes before a demo. Each push to `backend` redeploys automatically and runs any new migrations.

## Part 3: The site URL for offer links (2 minutes, once Tyler publishes)

Offer links and QR codes use `app_settings.public_base_url`. In Supabase → **SQL Editor**, run:

```sql
update app_settings set value = 'https://<tyler-published-site>' where key = 'public_base_url';
```

Existing drafts pick up the new address automatically.

## Part 4: Real sign-in (later, when the team confirms D1)

1. Supabase → **Authentication** → **Sign In / Providers**: Email on, **Allow new users to sign up: off**.
2. Supabase → **Authentication** → **URL Configuration**: add Tyler's preview and published URLs as redirect URLs.
3. Put `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in your `.env` (Mac only), then create accounts:
   ```bash
   python -m feng_workers.users add manager@example.com --role manager --locations sunnyvale --name "Manager"
   python -m feng_workers.users add staff@example.com --role staff --locations sunnyvale --password '<a strong password>'
   python -m feng_workers.users add you@example.com --role admin --locations sunnyvale
   ```
4. On Render, set `AUTH_MODE=supabase` (and check `SUPABASE_URL` / `SUPABASE_ANON_KEY` are set). Tyler's app then sends the signed-in user's token instead of `X-Dev-Key`.

## If something fails

| Symptom | Likely cause |
|---|---|
| `migrate` says "Tables already exist but no migrations are recorded" | The schema was pasted into the SQL editor by hand earlier. Run `python -m feng_workers.migrate --baseline-through <last file you pasted>` |
| Render deploy log: `connection ... failed` / `Network is unreachable` | `DATABASE_URL` is the Direct connection string; use the Session pooler one |
| Render deploy log: `password authentication failed` | `[YOUR-PASSWORD]` not replaced, or a special character in the password needs URL-encoding (e.g. `@` → `%40`) |
| Tyler's app shows a CORS error in the browser console | His exact URL isn't in `CORS_ORIGINS`; add it on Render (Environment) and save, which restarts the service |
| `401 Missing or wrong X-Dev-Key` | The frontend isn't sending `X-Dev-Key`, or the value differs from Render's `DEV_ACCESS_KEY` |
