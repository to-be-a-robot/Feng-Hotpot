from __future__ import annotations

import psycopg
import pytest

from feng_workers.config import REPO_ROOT


@pytest.fixture(scope="session")
def db_url(tmp_path_factory):
    """Embedded Postgres (with pgvector) with every migration applied, in order."""
    pgserver = pytest.importorskip("pgserver")
    srv = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    url = srv.get_uri()
    with psycopg.connect(url, autocommit=True) as conn:
        for m in sorted((REPO_ROOT / "supabase" / "migrations").glob("*.sql")):
            conn.execute(m.read_text())
    yield url
    srv.cleanup()


@pytest.fixture
def conn(db_url):
    with psycopg.connect(db_url, autocommit=True) as c:
        yield c
