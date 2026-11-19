# Seed data

The backend loads three CSV files from one folder (`SEED_DIR` in `.env`; default `seed/example`, which is fictional).
`seed/template/` has the exact headers with one illustrative row each: copy it, replace the rows, and keep the headers.

```bash
cd workers && source .venv/bin/activate
python -m feng_workers.load_seed --dir ../seed/real --dry-run   # check every row; nothing is written
python -m feng_workers.load_seed --dir ../seed/real             # load (safe to re-run: updates, never duplicates)
python -m feng_workers.embed && python -m feng_workers.scoring
```

## creators.csv: one row per platform account

| Column | Required | Notes |
|---|---|---|
| `creator_id` | recommended | Your id, e.g. `c_001`. Must match `creator_id` in the hand-label sheet, which is how the evaluation finds them |
| `handle` | yes | With or without `@`. Xiaohongshu display names like `Venussss (ID 27735966362)` are fine |
| `display_name` | no | |
| `platform` | yes | `instagram`, `tiktok`, `xiaohongshu` (also accepts `IG`, `TT`, `XHS`, `RedNote`, `小红书`) |
| `profile_url` | no | Must start with `https://` |
| `city` | no | Home city (`Palo Alto`, `Bay Area`, `South Bay`...). Used for the Creators location filter and the locality score |
| `followers` | no | `13.4k`, `12,000`, `1.2万`, or annotated like `619 (32.9k likes+saves)`: the first number is used |
| `source` | **yes** | Where the row came from, e.g. `hand-collected 2026-11-18 (Aolin)`. Rows without a source are rejected |
| `bio` | recommended | Profile bio text. Helps the scorer catch locality traps (moved away, 大湾区, IP location elsewhere: put that in the bio, e.g. `IP: 广东`) |

## creator_posts.csv: recent posts (5–10 per creator)

| Column | Required | Notes |
|---|---|---|
| `platform`, `handle` | yes | Must match a row in creators.csv |
| `url` | **yes** | The post link; used to avoid duplicates on reload |
| `caption` | strongly recommended | Original language. The scorer and the draft writer read it |
| `lang` | no | `en` / `zh` |
| `posted_at` | recommended | `2026-11-10` or `2026-11-10T19:30` |
| `likes`, `comments` | recommended | Counts; same number formats as followers |
| `source` | **yes** | |

## brand_corpus.csv: Feng Hotpot's own voice

| Column | Required | Notes |
|---|---|---|
| `kind` | yes | `tone`, `menu`, `post` or `location`. `tone` and `post` shape the outreach voice |
| `text` | yes | |
| `lang` | no | `en` / `zh` |
| `source` | **yes** | |

Values with commas must be in double quotes (`"like, this"`); the loader stops with the line number if one isn't.
Different column names are fine too: map them in `config/seed_columns.json` instead of renaming.
