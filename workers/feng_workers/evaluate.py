"""Model evaluation for the pitch.

    python -m feng_workers.evaluate --labels seed/labels.csv

1. Ranking: precision@10 of our creator ranking against hand labels.
   labels.csv: Aolin's sheet. Matched on `creator_id` (= creators.external_id
   from the seed) when present, otherwise on platform + handle.
   label: 1/0, yes/no or good/bad. Rows with a blank label are skipped.
   precision@10 = share of our top 10 (among labeled creators) that are labeled good.
2. Drafts (from the audit log): acceptance rate = approved ÷ (approved + rejected),
   and the share approved without any edits.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .load_seed import normalize_handle, normalize_platform
from .config import load_config

GOOD = {"1", "yes", "y", "good", "true", "fit"}
BAD = {"0", "no", "n", "bad", "false", "no fit"}


def read_labels(path: Path) -> tuple[dict[str, bool], list[str]]:
    """Returns ({key: is_good}, [rows without a usable label]). Keys are
    'id:<creator_id>' or 'ph:<platform>/<handle>'."""
    aliases = {k.lower(): v for k, v in load_config("seed_columns").get("platform_aliases", {}).items()}
    labels, unlabeled = {}, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            key = (f"id:{r['creator_id'].strip()}" if (r.get("creator_id") or "").strip()
                   else f"ph:{normalize_platform(r['platform'], aliases)}/{normalize_handle(r['handle'])}")
            value = (r.get("label") or "").strip().lower()
            if value in GOOD or value in BAD:
                labels[key] = value in GOOD
            else:
                unlabeled.append(f"{key} ({r.get('handle', '').strip()})")
    return labels, unlabeled


def ranking_eval(conn, labels: dict[str, bool], k: int = 10, unlabeled: list[str] | None = None) -> dict:
    ranked = conn.execute(
        "select external_id, platform, handle, score from creators where score is not null "
        "order by score desc, handle").fetchall()

    def key_of(ext, p, h):
        return f"id:{ext}" if ext and f"id:{ext}" in labels else f"ph:{p}/{h}"

    labeled = [(key_of(e, p, h), p, h, s) for e, p, h, s in ranked if key_of(e, p, h) in labels]
    top = labeled[:k]
    found = {x[0] for x in labeled}
    return {
        "labeled_and_scored": len(labeled),
        "k": len(top),
        "precision_at_k": round(sum(labels[key] for key, *_ in top) / len(top), 3) if top else None,
        "base_rate": round(sum(labels.values()) / len(labels), 3) if labels else None,
        "top_k": [{"creator": f"{p}/@{h}", "label_key": key, "score": float(s), "label_good": labels[key]}
                  for key, p, h, s in top],
        "labels_not_found_or_unscored": sorted(set(labels) - found),
        "rows_without_label": unlabeled or [],
    }


def draft_eval(conn) -> dict:
    # Latest decision per message, so a reopen-then-approve counts once.
    row = conn.execute(
        """
        with decisions as (
          select distinct on (entity_id) entity_id, action, (meta ->> 'edited')::boolean as edited
          from audit_log where action in ('outreach.approve', 'outreach.reject')
          order by entity_id, at desc)
        select count(*) filter (where action = 'outreach.approve'),
               count(*) filter (where action = 'outreach.reject'),
               count(*) filter (where action = 'outreach.approve' and not coalesce(edited, false))
        from decisions
        """).fetchone()
    approved, rejected, unedited = row
    decided = approved + rejected
    return {"approved": approved, "rejected": rejected,
            "acceptance_rate": round(approved / decided, 3) if decided else None,
            "approved_without_edits_rate": round(unedited / approved, 3) if approved else None}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", type=Path, help="hand-label CSV (Aolin's 20 creators)")
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args(argv)
    from .db import connect
    from .llm import to_json
    with connect() as conn:
        out = {"drafts": draft_eval(conn)}
        if args.labels:
            labels, unlabeled = read_labels(args.labels)
            if not labels:
                raise SystemExit(f"{args.labels}: no row has a label yet ({len(unlabeled)} blank). "
                                 "Fill the label column with good/bad (or 1/0).")
            out["ranking"] = ranking_eval(conn, labels, args.k, unlabeled)
        else:
            out["ranking"] = "skipped: pass --labels <csv>"
    print(to_json(out))


if __name__ == "__main__":
    main()
