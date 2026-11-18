"""Embed creator captions and the brand corpus.

    python -m feng_workers.embed          # only rows missing an embedding from the current model
    python -m feng_workers.embed --all    # re-embed everything

Rows embedded by a different model (see `embedding_model`) count as missing,
so switching EMBEDDING_PROVIDER/EMBEDDING_MODEL and re-running converges.
"""

from __future__ import annotations

import argparse

from .db import connect
from .embeddings import BATCH_SIZE, Embedder, get_embedder

# table -> column holding the text to embed
TARGETS = {"creator_posts": "caption", "brand_corpus": "text"}


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.7g}" for v in vec) + "]"


def embed_table(conn, embedder: Embedder, table: str, text_col: str, *, force: bool) -> int:
    where = f"{text_col} is not null and length(trim({text_col})) > 0"
    if not force:
        where += " and (embedding is null or embedding_model is distinct from %(model)s)"
    with conn.cursor() as cur:
        cur.execute(f"select id, {text_col} from {table} where {where} order by id", {"model": embedder.name})
        rows = cur.fetchall()

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        vectors = embedder.embed([text for _, text in batch])
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                f"update {table} set embedding = %s::vector, embedding_model = %s where id = %s",
                [(to_pgvector(v), embedder.name, row_id) for (row_id, _), v in zip(batch, vectors)],
            )
    return len(rows)


def run(conn, embedder: Embedder | None = None, *, force: bool = False) -> dict[str, int]:
    embedder = embedder or get_embedder()
    return {t: embed_table(conn, embedder, t, col, force=force) for t, col in TARGETS.items()}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="re-embed every row")
    args = ap.parse_args(argv)
    embedder = get_embedder()
    if embedder.name.startswith("fake:"):
        print("WARNING: EMBEDDING_PROVIDER=fake — vectors are for wiring only, not real similarity.")
    with connect() as conn:
        counts = run(conn, embedder, force=args.all)
    print(f"Embedded with {embedder.name}: {counts}")


if __name__ == "__main__":
    main()
