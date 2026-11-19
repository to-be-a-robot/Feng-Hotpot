from __future__ import annotations

import psycopg

from .config import env


# prepare_threshold=None: no server-side prepared statements, so the Supabase
# pooler works in either mode (transaction mode on port 6543 doesn't support them).
CONNECT_KWARGS = {"prepare_threshold": None}


def connect(url: str | None = None, **kwargs) -> psycopg.Connection:
    return psycopg.connect(url or env("DATABASE_URL", required=True), **{**CONNECT_KWARGS, **kwargs})
