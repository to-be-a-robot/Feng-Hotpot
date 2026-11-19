"""Apply supabase/migrations/*.sql in order, once each.

    python -m feng_workers.migrate              # uses DATABASE_URL
    python -m feng_workers.migrate --status     # list applied / pending
    python -m feng_workers.migrate --baseline-through 20261118000004_api_functions.sql
                                                # DB set up by hand: mark files up to and including
                                                # that one as applied, then apply the rest

Applied files are recorded in public.schema_migrations, so re-running only
applies new files. Each file runs in its own transaction.

Supabase: use the *session* connection string (port 5432), not the
transaction pooler (6543), because migrations send several statements at once.
"""

from __future__ import annotations

import argparse

import psycopg

from .config import REPO_ROOT
from .db import CONNECT_KWARGS

MIGRATIONS = REPO_ROOT / "supabase" / "migrations"


def _ensure_table(conn):
    conn.execute("create table if not exists public.schema_migrations "
                 "(name text primary key, applied_at timestamptz not null default now())")
    conn.execute("alter table public.schema_migrations enable row level security")


def status(conn) -> tuple[list[str], list[str]]:
    _ensure_table(conn)
    done = {r[0] for r in conn.execute("select name from public.schema_migrations")}
    files = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    return [f for f in files if f in done], [f for f in files if f not in done]


def apply(url: str, *, baseline_through: str | None = None) -> list[str]:
    """Apply pending files. With baseline_through, files up to and including
    that name are only recorded (they were applied by hand earlier)."""
    applied = []
    with psycopg.connect(url, autocommit=True, **CONNECT_KWARGS) as conn:
        done, pending = status(conn)
        if baseline_through and baseline_through not in {p.name for p in MIGRATIONS.glob("*.sql")}:
            raise SystemExit(f"No migration named {baseline_through}")
        if pending and not done and not baseline_through and \
                conn.execute("select to_regclass('public.creators')").fetchone()[0]:
            raise SystemExit("Tables already exist but no migrations are recorded (set up by hand?). "
                             "Run with --baseline-through <last file you applied>, or reset the database.")
        for name in pending:
            record_only = baseline_through is not None and name <= baseline_through
            with conn.transaction():
                if not record_only:
                    conn.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
                conn.execute("insert into public.schema_migrations (name) values (%s)", (name,))
            applied.append(name + (" (recorded only)" if record_only else ""))
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--baseline-through", metavar="FILE")
    args = ap.parse_args(argv)
    from .config import env
    url = env("DATABASE_URL", required=True)
    if args.status:
        with psycopg.connect(url, autocommit=True, **CONNECT_KWARGS) as conn:
            done, pending = status(conn)
        print("Applied:", *done or ["(none)"], sep="\n  ")
        print("Pending:", *pending or ["(none)"], sep="\n  ")
        return
    applied = apply(url, baseline_through=args.baseline_through)
    print(f"Applied: {', '.join(applied)}" if applied else "Up to date.")


if __name__ == "__main__":
    main()
