from __future__ import annotations

import psycopg

from .config import env


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or env("DATABASE_URL", required=True))
