"""One-off: move stored ColBERT vectors from the JSON text column to binary.

Why: ColBERT produces one vector per token, so a ~400-token memory was ~9 MB of
JSON text per row and cost ~0.19s per row just to parse back. With ~55 candidates
per recall that was ~10s of pure parsing on every analysis cycle.

Safe to re-run: rows that already have binary are skipped. The readable `text`
column is never touched — the vectors are derived data and could also be
regenerated from it, so the worst case here is "convert again", not data loss.

Usage:  .venv/Scripts/python.exe scripts/migrate_colbert_to_binary.py [--dry-run]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lancedb  # noqa: E402
import pyarrow as pa  # noqa: E402

from openforexai.services.semantic_memory_service import (  # noqa: E402
    _COLBERT_BIN_FIELD,
    _pack_colbert,
)

_DB_PATH = Path("data/semantic_memory")


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    if not _DB_PATH.exists():
        print(f"No semantic memory store at {_DB_PATH} — nothing to do.")
        return 0

    db = lancedb.connect(str(_DB_PATH))
    table_names = list(db.table_names())
    print(f"{'DRY RUN — ' if dry_run else ''}tables: {table_names}\n")

    total_converted = 0
    for name in table_names:
        tbl = db.open_table(name)

        if _COLBERT_BIN_FIELD not in tbl.schema.names:
            print(f"[{name}] adding column {_COLBERT_BIN_FIELD}")
            if not dry_run:
                tbl.add_columns(pa.field(_COLBERT_BIN_FIELD, pa.large_binary()))

        rows = tbl.search().limit(100_000).to_list()
        pending = [
            r for r in rows
            if not r.get(_COLBERT_BIN_FIELD) and (r.get("colbert_vecs") or "").strip()
        ]
        print(f"[{name}] rows={len(rows)} to convert={len(pending)}")
        if not pending:
            continue

        started = time.perf_counter()
        updates = []
        for r in pending:
            vecs = json.loads(r["colbert_vecs"])
            updates.append({
                "id": r["id"],
                _COLBERT_BIN_FIELD: _pack_colbert(vecs),
                # Drop the JSON now that the binary form carries it — keeping both
                # would leave ~9 MB per row that nothing reads.
                "colbert_vecs": "",
            })

        if not dry_run:
            # merge_insert matches on id and updates only the listed columns,
            # so text/tags/vector/metadata stay exactly as they are.
            (tbl.merge_insert("id")
                .when_matched_update_all()
                .execute(updates))
        elapsed = time.perf_counter() - started
        total_converted += len(updates)
        print(f"[{name}] converted {len(updates)} rows in {elapsed:.1f}s")

    print(f"\n{'Would convert' if dry_run else 'Converted'} {total_converted} rows total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
