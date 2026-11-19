"""Applies the real migrations to an embedded Postgres, then loads and embeds the example seed."""

from __future__ import annotations

import shutil
from pathlib import Path

import psycopg
import pytest

from feng_workers import embed, load_seed
from feng_workers.config import REPO_ROOT
from feng_workers.embeddings import FakeEmbedder

EXAMPLE = REPO_ROOT / "seed" / "example"


# ----------------------------------------------------------------- pure parsing

@pytest.mark.parametrize("raw,expected", [
    ("12000", 12000), ("12,000", 12000), ("12.4k", 12400), ("1.2M", 1_200_000), ("1.5万", 15000), ("", None),
    ("619 (32.9k likes+saves)", 619), ("11k (1,035 notes)", 11000), ("368.5k (21.5M likes)", 368500),
])
def test_parse_count(raw, expected):
    assert load_seed.parse_count(raw) == expected


def test_platform_aliases_and_handles():
    assert load_seed.normalize_platform("XHS", {"xhs": "xiaohongshu"}) == "xiaohongshu"
    assert load_seed.normalize_handle(" @Some_Creator ") == "some_creator"
    with pytest.raises(ValueError):
        load_seed.normalize_platform("myspace", {})


def test_bad_rows_are_all_reported_and_nothing_loads(tmp_path: Path):
    for f in EXAMPLE.iterdir():
        shutil.copy(f, tmp_path)
    with open(tmp_path / "creators.csv", "a", encoding="utf-8") as f:
        f.write(",no_source_creator,X,instagram,,Sunnyvale,10,,\n")
        f.write(",bad_platform,X,myspace,,Sunnyvale,10,somewhere,\n")
    with pytest.raises(load_seed.SeedError) as e:
        load_seed.read_seed(tmp_path)
    assert "creators.csv:7: source is empty" in str(e.value)
    assert "creators.csv:8: unknown platform" in str(e.value)


# ----------------------------------------------------------------- database

def test_unquoted_comma_is_caught(tmp_path: Path):
    for f in EXAMPLE.iterdir():
        shutil.copy(f, tmp_path)
    with open(tmp_path / "creators.csv", "a", encoding="utf-8") as f:
        f.write(",comma_creator,X,instagram,,Sunnyvale,10,hand-collected, Nov 16,\n")
    with pytest.raises(load_seed.SeedError, match="unquoted comma"):
        load_seed.read_seed(tmp_path)


def counts(conn):
    # Filter by source: other test files share this database.
    return {t: conn.execute(f"select count(*) from {t} where source like 'EXAMPLE%%'").fetchone()[0]
            for t in ("creators", "creator_posts", "brand_corpus")}


def test_load_is_idempotent_and_keeps_sources(db_url):
    data = load_seed.read_seed(EXAMPLE)
    with psycopg.connect(db_url) as conn:
        load_seed.write_seed(conn, data)
        first = counts(conn)
        load_seed.write_seed(conn, data)
        assert counts(conn) == first == {"creators": 5, "creator_posts": 6, "brand_corpus": 4}
        assert conn.execute("select count(*) from creator_posts where source like 'EXAMPLE%'").fetchone()[0] == 6
        assert conn.execute(
            "select platform, followers from creators where handle = 'example_xhs_foodie'"
        ).fetchone() == ("xiaohongshu", 8500)


def test_embed_then_caption_change_clears_embedding(db_url):
    with psycopg.connect(db_url) as conn:
        load_seed.write_seed(conn, load_seed.read_seed(EXAMPLE))
        # Other test files add rows to this shared database, so compare to the first run.
        done = embed.run(conn, FakeEmbedder(dim=32), force=True)
        assert done["creator_posts"] >= 6 and done["brand_corpus"] >= 4
        assert embed.run(conn, FakeEmbedder(dim=32)) == {"creator_posts": 0, "brand_corpus": 0}

        # Similarity query works on stored vectors.
        row = conn.execute(
            "select b.kind, p.embedding <=> b.embedding from creator_posts p, brand_corpus b limit 1"
        ).fetchone()
        assert row[1] is not None

        # Changing a caption clears just that row's embedding.
        data = load_seed.read_seed(EXAMPLE)
        data.posts[0]["caption"] = "edited caption"
        load_seed.write_seed(conn, data)
        assert embed.run(conn, FakeEmbedder(dim=32)) == {"creator_posts": 1, "brand_corpus": 0}

        # Switching model re-embeds everything.
        assert embed.run(conn, FakeEmbedder(dim=16)) == done
