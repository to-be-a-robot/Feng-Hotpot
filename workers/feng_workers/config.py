"""Shared settings. Everything a teammate might change lives in .env or /config."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"

load_dotenv(REPO_ROOT / ".env")


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"Missing environment variable {name}. Copy .env.example to .env and set it.")
    return value


def load_config(name: str) -> dict:
    """Read /config/<name>.json."""
    with open(CONFIG_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def seed_dir() -> Path:
    path = Path(env("SEED_DIR", "seed/example"))
    return path if path.is_absolute() else REPO_ROOT / path
