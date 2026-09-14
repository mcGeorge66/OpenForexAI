"""One-off: fill in pnl_pips for order book entries closed before it was computed.

The field existed in the model, the schema and the API from the start, but
nothing ever wrote it — every closed trade carried an empty column while the
Examiner agent reasoned about results. Closing entries fill it in from now on
(RepositoryService._with_pnl_pips); this catches up the history, which has the
prices needed to derive it.

Idempotent: entries that already have a value are skipped, so a second run is
a no-op. Prints a summary and does nothing without --apply.

    python scripts/backfill_pnl_pips.py            # dry run
    python scripts/backfill_pnl_pips.py --apply
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from openforexai.config.json_loader import load_json_config, resolve_config_path  # noqa: E402
from openforexai.data.normalizer import pnl_in_pips  # noqa: E402


def _decimal(value) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the values (default: dry run)")
    args = parser.parse_args()

    cfg = load_json_config(resolve_config_path(_ROOT / "config"))
    db_path = Path(str(cfg.get("database", {}).get("sqlite_path", "./data/openforexai.db")))
    if not db_path.is_absolute():
        db_path = (_ROOT / db_path).resolve()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, pair, direction, fill_price, close_price, pnl_pips
           FROM order_book_entries
           WHERE status = 'CLOSED' AND (pnl_pips IS NULL OR pnl_pips = '')"""
    ).fetchall()

    computed: list[tuple[str, str]] = []
    skipped_no_price = 0
    for r in rows:
        value = pnl_in_pips(
            r["pair"] or "", r["direction"] or "",
            _decimal(r["fill_price"]), _decimal(r["close_price"]),
        )
        if value is None:
            skipped_no_price += 1
            continue
        computed.append((str(value), r["id"]))

    print(f"Datenbank:            {db_path}")
    print(f"geschlossen ohne Wert: {len(rows)}")
    print(f"berechenbar:           {len(computed)}")
    print(f"ohne Kurs, bleibt leer:{skipped_no_price}")

    if computed:
        print("\nStichprobe:")
        for r in rows[:5]:
            value = pnl_in_pips(
                r["pair"] or "", r["direction"] or "",
                _decimal(r["fill_price"]), _decimal(r["close_price"]),
            )
            print(f"  {r['pair']:7s} {r['direction']:4s} "
                  f"{str(r['fill_price'])[:9]:>9s} -> {str(r['close_price'])[:9]:>9s}  = {value}")

    if not args.apply:
        print("\nTrockenlauf — mit --apply schreiben.")
        return 0

    conn.executemany("UPDATE order_book_entries SET pnl_pips = ? WHERE id = ?", computed)
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM order_book_entries WHERE status='CLOSED' AND (pnl_pips IS NULL OR pnl_pips='')"
    ).fetchone()[0]
    print(f"\n{len(computed)} Einträge geschrieben. Ohne Wert verbleiben: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
