"""One-shot migration: relabel broker-sourced timestamps from +00:00 to +03:00.

Background
----------
The MT5 adapter used to call `datetime.fromtimestamp(raw, tz=UTC)`. The raw
value is broker-local wall-clock time, so the hour values were correct but the
timezone label was wrong (UTC instead of UTC+3).

After the source-code fix (_broker_timestamp now relabels to broker_tz) new
timestamps will be stored as +03:00. This script migrates already-stored data
so the entire database is consistent.

Tables migrated
---------------
1. All OXS_T_*_M5 candle tables — every row's timestamp column.
2. order_book_entries — only broker-sourced columns (opened_at, closed_at).
   Locally-sourced timestamps (requested_at, close_requested_at,
   last_broker_sync) stay untouched: they were set via datetime.now(UTC) and
   are real UTC.

The script is idempotent: rows whose timestamps already carry +03:00 are
skipped.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "openforexai.db"
OLD_TZ = "+00:00"
NEW_TZ = "+03:00"


def migrate_candle_tables(con: sqlite3.Connection) -> None:
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'OXS_T_%_M5'"
    )
    tables = [row[0] for row in cur.fetchall()]
    if not tables:
        print("  (no OXS_T candle tables found)")
        return
    for table in tables:
        affected = con.execute(
            f"UPDATE {table} SET timestamp = REPLACE(timestamp, ?, ?) "
            f"WHERE timestamp LIKE '%{OLD_TZ}'",
            (OLD_TZ, NEW_TZ),
        ).rowcount
        print(f"  {table:30s} --> {affected} rows updated")


def migrate_order_book(con: sqlite3.Connection) -> None:
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='order_book_entries'"
    )
    if not cur.fetchone():
        print("  (no order_book_entries table)")
        return

    affected_open = con.execute(
        "UPDATE order_book_entries SET opened_at = REPLACE(opened_at, ?, ?) "
        f"WHERE broker_name='OXS_T' AND opened_at LIKE '%{OLD_TZ}'",
        (OLD_TZ, NEW_TZ),
    ).rowcount
    affected_close = con.execute(
        "UPDATE order_book_entries SET closed_at = REPLACE(closed_at, ?, ?) "
        f"WHERE broker_name='OXS_T' AND closed_at LIKE '%{OLD_TZ}'",
        (OLD_TZ, NEW_TZ),
    ).rowcount
    print(f"  order_book_entries.opened_at --> {affected_open} rows updated")
    print(f"  order_book_entries.closed_at --> {affected_close} rows updated")


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH}")
        return 1
    print(f"DB: {DB_PATH}")
    print(f"Relabel {OLD_TZ} --> {NEW_TZ} for broker-sourced columns\n")

    con = sqlite3.connect(str(DB_PATH))
    try:
        print("Candle tables:")
        migrate_candle_tables(con)
        print("\nOrder book entries:")
        migrate_order_book(con)
        con.commit()
        print("\nDone.")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
