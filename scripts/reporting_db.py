"""Build, refresh and inspect the reporting database.

    .venv/Scripts/python.exe scripts/reporting_db.py --sync
    .venv/Scripts/python.exe scripts/reporting_db.py --status
    .venv/Scripts/python.exe scripts/reporting_db.py --rebuild

--sync runs one incremental pass (the same one the DataContainer runs in the
background). --status shows how current each table is and whether the last
pass failed. --rebuild throws the file away and starts over; it is derived
data, so that is always safe.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openforexai.data import reporting_db as rdb
from openforexai.data.reporting_sync import sync_all

PROD = Path(__file__).resolve().parents[1] / "data" / "openforexai.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()

    if a.rebuild:
        if rdb.DEFAULT_PATH.exists():
            size = rdb.DEFAULT_PATH.stat().st_size / 1048576
            rdb.DEFAULT_PATH.unlink()
            for suffix in ("-wal", "-shm"):
                p = Path(str(rdb.DEFAULT_PATH) + suffix)
                if p.exists():
                    p.unlink()
            print(f"verworfen ({size:.0f} MB) — wird neu gebaut")
        a.sync = True

    if a.sync:
        t0 = time.perf_counter()
        # A pass is capped per table, so a first build walks through in
        # batches. It never reaches zero — live candles keep arriving while it
        # runs — so it stops once a pass only picks up that trickle.
        AUFGEHOLT = 500
        runde = 0
        while True:
            runde += 1
            counts = sync_all(PROD)
            neu = sum(v for k, v in counts.items() if k != "trades")
            print(f"  Durchlauf {runde}: {neu} Kerzen/Schluessel, "
                  f"{counts.get('trades', 0)} Trades")
            if neu < AUFGEHOLT or runde >= 20:
                break
        print(f"fertig in {time.perf_counter()-t0:.0f}s")
        a.status = True

    if a.status:
        con = rdb.connect()
        rows = rdb.status(con)
        if not rows:
            print("leer — mit --sync fuellen")
            return
        size = rdb.DEFAULT_PATH.stat().st_size / 1048576
        print(f"\n{rdb.DEFAULT_PATH}  ({size:.0f} MB)")
        print(f"{'Tabelle':28s}{'Zeilen':>9s}  {'bis':17s}{'Fehler'}")
        print("-" * 72)
        for r in rows:
            mark = (r["watermark"] or "-")[:16]
            print(f"{r['table_name']:28s}{r['rows']:>9d}  {mark:17s}"
                  f"{r['last_error'] or ''}")
        con.close()


if __name__ == "__main__":
    main()
