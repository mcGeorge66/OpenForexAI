"""Reading candles out of the reporting mirror.

The simulation reads here and only here. Two reasons, and the second is the
one that matters.

Speed: every timeframe is materialised, so an M15 or H1 window is a table read
instead of an aggregation over M5. A simulation stepping through thousands of
positions pays that on every single step.

Certainty about what was simulated: a run that can silently fall back to the
live database produces numbers nobody can place afterwards. So there is no
fallback. A missing mirror raises, and the message says how to build it —
being told to run one command beats discovering next week that half a study
ran against different data.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from openforexai.data import reporting_db as rdb
from openforexai.models.market import Candle


class ReportingUnavailable(RuntimeError):
    """The mirror is missing, empty or has no data for this pair."""


class ReportingReader:
    """Read-only access to reporting.db. Cheap to create, safe to keep."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else rdb.DEFAULT_PATH
        self._con: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._con is None:
            if not self._path.exists():
                raise ReportingUnavailable(
                    f"Reporting database missing at {self._path}. "
                    "Build it with: python scripts/reporting_db.py --sync"
                )
            self._con = sqlite3.connect(
                f"file:{self._path.as_posix()}?mode=ro", uri=True, check_same_thread=False,
            )
            self._con.row_factory = sqlite3.Row
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int = 300,
        start: datetime | str | None = None,
    ) -> list[Candle]:
        """The newest *limit* candles at or before *start*, oldest first.

        Same contract as the production read — including that `start` means
        "as of", looking backwards — so a caller cannot tell the two apart
        except by being faster.
        """
        con = self._connect()
        table = rdb.table_name(broker_name, pair, timeframe)
        if not con.execute(
            "select 1 from sqlite_master where type='table' and name=? limit 1", (table,),
        ).fetchone():
            raise ReportingUnavailable(
                f"No {timeframe} data for {pair} in the reporting database ({table}). "
                "Run: python scripts/reporting_db.py --sync"
            )

        anchor = None
        if start is not None:
            anchor = start if isinstance(start, str) else start.isoformat()
        if anchor:
            rows = con.execute(
                f"select * from {table} where timestamp <= ? order by timestamp desc limit ?",
                (anchor, limit),
            ).fetchall()
        else:
            rows = con.execute(
                f"select * from {table} order by timestamp desc limit ?", (limit,),
            ).fetchall()
        if not rows:
            raise ReportingUnavailable(
                f"{table} holds nothing at or before {anchor or 'now'}."
            )

        from decimal import Decimal
        out = []
        for r in reversed(rows):
            # Null candles are placeholders for gaps and are dropped on the
            # production path too — a simulation must see the same series.
            if float(r["close"]) == 0:
                continue
            out.append(Candle(
                timestamp=datetime.fromisoformat(r["timestamp"]),
                open=Decimal(str(r["open"])), high=Decimal(str(r["high"])),
                low=Decimal(str(r["low"])), close=Decimal(str(r["close"])),
                tick_volume=int(r["tick_volume"] or 0),
                spread=Decimal(str(r["spread"])), timeframe=timeframe.upper(),
            ))
        return out

    def coverage(self, broker_name: str, pair: str, timeframe: str) -> dict:
        """What the mirror actually holds — so a simulation can say how
        current its data was instead of leaving that to be assumed."""
        con = self._connect()
        table = rdb.table_name(broker_name, pair, timeframe)
        row = con.execute(
            "select rows, watermark, synced_at from sync_state where table_name = ?",
            (table,),
        ).fetchone()
        return dict(row) if row else {"rows": 0, "watermark": None, "synced_at": None}
