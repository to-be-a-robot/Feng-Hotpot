"""Load the seed CSVs (creators, posts, brand corpus) into Postgres.

    python -m feng_workers.load_seed                 # uses SEED_DIR from .env
    python -m feng_workers.load_seed --dir path/     # explicit folder
    python -m feng_workers.load_seed --dry-run       # validate only, no DB needed

Column names come from config/seed_columns.json, so when Aolin's real CSVs
arrive with different headers you edit that file, not this code.

Behavior:
  * Every row must carry a `source`; the loader never invents one.
  * All rows are validated first. If any row fails, nothing is written.
  * Re-running is safe: creators upsert on (platform, handle), posts on
    (creator, url), brand corpus on (kind, text). When a caption or corpus text
    changes, its embedding is cleared so `embed` picks it up again.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config, seed_dir

PLATFORMS = {"tiktok", "instagram", "xiaohongshu"}


class SeedError(Exception):
    pass


@dataclass
class SeedData:
    creators: list[dict] = field(default_factory=list)
    posts: list[dict] = field(default_factory=list)
    brand: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- parsing helpers

def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_count(value: str | None) -> int | None:
    """'12000', '12,000', '12k', '1.2M', '1.2万', and annotated forms like
    '619 (32.9k likes+saves)' or '11k (1,035 notes)' -> int (the first number)."""
    value = _clean(value)
    if value is None:
        return None
    m = re.match(r"\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmMwW万]?)", value)
    if not m:
        raise ValueError(f"not a number: {value!r}")
    multipliers = {"k": 1_000, "m": 1_000_000, "万": 10_000, "w": 10_000}
    return int(round(float(m.group(1).replace(",", "")) * multipliers.get(m.group(2).lower(), 1)))


def parse_timestamp(value: str | None) -> datetime | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"not an ISO date/time (YYYY-MM-DD or YYYY-MM-DDTHH:MM): {value!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_https_url(value: str | None) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    if not value.startswith("https://") or len(value) > 2048:
        raise ValueError(f"profile/post links must start with https:// (got {value[:60]!r})")
    return value


def normalize_platform(value: str | None, aliases: dict[str, str]) -> str:
    v = (_clean(value) or "").lower()
    v = aliases.get(v, v)
    if v not in PLATFORMS:
        raise ValueError(f"unknown platform {value!r} (expected one of {sorted(PLATFORMS)})")
    return v


def normalize_handle(value: str | None) -> str:
    v = _clean(value)
    if not v:
        raise ValueError("handle is empty")
    return v.lstrip("@").lower()


# --------------------------------------------------------------------------- reading

def _read_rows(path: Path, columns: dict[str, str | None]) -> list[tuple[int, dict]]:
    """Return (line_number, {our_field: raw_value}) using the header mapping.

    A column mapped to null in config/seed_columns.json is treated as absent.
    """
    if not path.exists():
        raise SeedError(f"missing file: {path}")
    columns = {ours: theirs for ours, theirs in columns.items() if theirs}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = [csv_col for csv_col in columns.values() if csv_col not in headers]
        if missing:
            raise SeedError(
                f"{path.name}: missing columns {missing}. Found {sorted(headers)}. "
                "Update config/seed_columns.json to match the file's headers "
                "(set optional columns the file doesn't have to null)."
            )
        rows = []
        for line, row in enumerate(reader, start=2):
            if None in row:   # DictReader puts surplus fields under the key None
                raise SeedError(
                    f"{path.name}:{line}: more fields than headers — probably an unquoted comma. "
                    'Wrap that value in double quotes ("like, this").'
                )
            if any((v or "").strip() for v in row.values()):
                rows.append((line, {ours: row.get(theirs) for ours, theirs in columns.items()}))
        return rows


def read_seed(folder: Path) -> SeedData:
    cfg = load_config("seed_columns")
    aliases = {k.lower(): v for k, v in cfg.get("platform_aliases", {}).items()}
    errors: list[str] = []
    data = SeedData()

    def check(file: str, line: int, fn):
        try:
            return fn()
        except ValueError as e:
            errors.append(f"{file}:{line}: {e}")
            return None

    def require_source(raw: dict) -> str:
        s = _clean(raw.get("source"))
        if not s:
            raise ValueError("source is empty (every record needs a source)")
        return s

    # creators
    c = cfg["creators"]
    seen: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for line, raw in _read_rows(folder / c["file"], c["columns"]):
        row = check(c["file"], line, lambda: {
            "external_id": _clean(raw.get("external_id")),
            "bio": _clean(raw.get("bio")),
            "handle": normalize_handle(raw.get("handle")),
            "display_name": _clean(raw.get("display_name")),
            "platform": normalize_platform(raw.get("platform"), aliases),
            "profile_url": parse_https_url(raw.get("profile_url")),
            "city": _clean(raw.get("city")),
            "followers": parse_count(raw.get("followers")),
            "source": require_source(raw),
        })
        if row:
            key = (row["platform"], row["handle"])
            if key in seen:
                errors.append(f"{c['file']}:{line}: duplicate creator {key}")
            if row["external_id"] and row["external_id"] in seen_ids:
                errors.append(f"{c['file']}:{line}: duplicate creator_id {row['external_id']}")
            seen.add(key)
            seen_ids.add(row["external_id"])
            data.creators.append(row)

    # posts
    p = cfg["creator_posts"]
    for line, raw in _read_rows(folder / p["file"], p["columns"]):
        def build_post(raw=raw):
            key = (normalize_platform(raw.get("creator_platform"), aliases),
                   normalize_handle(raw.get("creator_handle")))
            if key not in seen:
                raise ValueError(f"post references unknown creator {key}")
            url = _clean(raw.get("url"))
            if not url:
                raise ValueError("url is empty (needed to de-duplicate posts on reload)")
            return {
                "creator_key": key,
                "url": url,
                "caption": _clean(raw.get("caption")),
                "lang": _clean(raw.get("lang")),
                "posted_at": parse_timestamp(raw.get("posted_at")),
                "likes": parse_count(raw.get("likes")),
                "comments": parse_count(raw.get("comments")),
                "source": require_source(raw),
            }
        row = check(p["file"], line, build_post)
        if row:
            data.posts.append(row)

    # brand corpus
    b = cfg["brand_corpus"]
    for line, raw in _read_rows(folder / b["file"], b["columns"]):
        def build_brand(raw=raw):
            kind = (_clean(raw.get("kind")) or "").lower()
            text = _clean(raw.get("text"))
            if not kind or not text:
                raise ValueError("kind and text are required")
            return {"kind": kind, "text": text, "lang": _clean(raw.get("lang")),
                    "source": require_source(raw)}
        row = check(b["file"], line, build_brand)
        if row:
            data.brand.append(row)

    if errors:
        raise SeedError("Seed validation failed — nothing was written:\n  " + "\n  ".join(errors))
    return data


# --------------------------------------------------------------------------- writing

def write_seed(conn, data: SeedData) -> dict[str, int]:
    with conn.transaction(), conn.cursor() as cur:
        ids: dict[tuple[str, str], str] = {}
        for r in data.creators:
            cur.execute(
                """
                insert into creators (external_id, handle, display_name, platform, profile_url, city, bio, followers, source)
                values (%(external_id)s, %(handle)s, %(display_name)s, %(platform)s, %(profile_url)s, %(city)s, %(bio)s,
                        %(followers)s, %(source)s)
                on conflict (platform, handle) do update set
                  external_id  = coalesce(excluded.external_id, creators.external_id),
                  bio          = excluded.bio,
                  display_name = excluded.display_name,
                  profile_url  = excluded.profile_url,
                  city         = excluded.city,
                  followers    = excluded.followers,
                  source       = excluded.source
                returning id
                """,
                r,
            )
            ids[(r["platform"], r["handle"])] = cur.fetchone()[0]

        for r in data.posts:
            cur.execute(
                """
                insert into creator_posts (creator_id, url, caption, lang, posted_at, likes, comments, source)
                values (%(creator_id)s, %(url)s, %(caption)s, %(lang)s, %(posted_at)s, %(likes)s, %(comments)s, %(source)s)
                on conflict (creator_id, url) do update set
                  embedding       = case when creator_posts.caption is distinct from excluded.caption
                                         then null else creator_posts.embedding end,
                  embedding_model = case when creator_posts.caption is distinct from excluded.caption
                                         then null else creator_posts.embedding_model end,
                  caption   = excluded.caption,
                  lang      = excluded.lang,
                  posted_at = excluded.posted_at,
                  likes     = excluded.likes,
                  comments  = excluded.comments,
                  source    = excluded.source
                """,
                {**r, "creator_id": ids[r["creator_key"]]},
            )

        for r in data.brand:
            # Text is part of the key, so a text change is a new row; old rows stay
            # until removed by hand (we never silently delete brand material).
            cur.execute(
                """
                insert into brand_corpus (kind, text, lang, source)
                values (%(kind)s, %(text)s, %(lang)s, %(source)s)
                on conflict (kind, md5(text)) do update set
                  lang = excluded.lang, source = excluded.source
                """,
                r,
            )
    return {"creators": len(data.creators), "creator_posts": len(data.posts), "brand_corpus": len(data.brand)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, help="folder with the seed CSVs (default: SEED_DIR)")
    ap.add_argument("--dry-run", action="store_true", help="validate only; don't touch the database")
    args = ap.parse_args(argv)

    folder = args.dir or seed_dir()
    try:
        data = read_seed(folder)
    except SeedError as e:
        raise SystemExit(str(e))

    counts = {"creators": len(data.creators), "creator_posts": len(data.posts), "brand_corpus": len(data.brand)}
    if args.dry_run:
        print(f"OK (dry run) — {folder}: {counts}")
        return

    from .db import connect
    with connect() as conn:
        counts = write_seed(conn, data)
    print(f"Loaded from {folder}: {counts}")


if __name__ == "__main__":
    main()
