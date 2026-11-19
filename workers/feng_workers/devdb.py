"""Local Postgres (with pgvector) for trying the backend without Supabase.

    python -m feng_workers.devdb            # start (if needed), apply migrations, print DATABASE_URL
    python -m feng_workers.devdb --reset    # wipe it and start fresh
    python -m feng_workers.devdb --stop     # stop the server

Data lives in ~/.feng-hotpot-devdb (outside the project: the embedded Postgres
can't start from a path with spaces). Needs the dev extras: pip install -e ".[dev]".
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import psycopg

from .config import REPO_ROOT

DATA_DIR = Path.home() / ".feng-hotpot-devdb"


def server(cleanup_mode=None):
    import pgserver   # dev dependency
    return pgserver.get_server(DATA_DIR, cleanup_mode=cleanup_mode)


def migrate(url: str) -> list[str]:
    applied = []
    with psycopg.connect(url, autocommit=True) as conn:
        if conn.execute("select to_regclass('public.creators')").fetchone()[0]:
            return applied      # already set up; use --reset to start over
        for m in sorted((REPO_ROOT / "supabase" / "migrations").glob("*.sql")):
            conn.execute(m.read_text(encoding="utf-8"))
            applied.append(m.name)
    return applied


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args(argv)

    if args.stop or args.reset:
        if DATA_DIR.exists():
            server(cleanup_mode="stop").cleanup()
        if args.stop:
            print("Stopped.")
            return
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    url = server().get_uri()
    applied = migrate(url)
    print(f"Applied: {', '.join(applied)}" if applied else "Database already set up.")
    print("\nPut this in .env (or export it):\n")
    print(f"DATABASE_URL={url}")


if __name__ == "__main__":
    main()
