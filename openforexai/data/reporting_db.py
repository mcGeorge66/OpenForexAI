"""The reporting database: production, mirrored, with the higher timeframes ready.

Production stores M5 only and aggregates M15/M30/H1/H4/D1 on every request.
For the UI that is free — one window, once. For a sweep over tens of thousands
of candles it is the single largest cost: measured at ~10 ms per market key,
almost all of it re-aggregating the same bars over and over.

This file holds the same candles with every timeframe materialised, the market
keys beside them, and a flat trade table. It is derived: it can be thrown away
and rebuilt from production at any time, so nothing here is ever the only copy
of anything.

Kept in sync incrementally by the DataContainer. Sync failures are logged and
never touch the candle path — the reporting copy falling behind must not cost
a single live candle. What it must not do is fall behind silently, so the
watermark per table is queryable and the repair is one command.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Everything the measuring instrument reads. M5 is copied, the rest aggregated
# from it with production's own resampler so the numbers cannot diverge.
TIMEFRAMES = ("M5", "M15", "M30", "H1", "H4", "D1")
TF_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "reporting.db"


def table_name(broker: str, pair: str, timeframe: str) -> str:
    def clean(s: str) -> str:
        return "".join(c if (c.isalnum() or c == "_") else "_" for c in s)
    return f"{clean(broker.upper())}_{clean(pair.upper())}_{clean(timeframe.upper())}"


CANDLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    timestamp   TEXT PRIMARY KEY,
    open        TEXT NOT NULL,
    high        TEXT NOT NULL,
    low         TEXT NOT NULL,
    close       TEXT NOT NULL,
    tick_volume INTEGER NOT NULL,
    spread      TEXT NOT NULL
);
"""

KEYS_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    timestamp    TEXT NOT NULL,
    param_set    TEXT NOT NULL,
    fomak        TEXT NOT NULL,
    fomak_text   TEXT,
    fopok        TEXT,
    fopok_text   TEXT,
    raw_values   TEXT,
    computed_at  TEXT NOT NULL,
    PRIMARY KEY (timestamp, param_set)
);
"""

# One row per trade with the market state at entry already joined — the join
# every analysis did by hand, done once.
TRADES_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    broker_order_id TEXT PRIMARY KEY,
    pair            TEXT NOT NULL,
    direction       TEXT NOT NULL,
    requested_at    TEXT NOT NULL,
    opened_at       TEXT,
    closed_at       TEXT,
    units           REAL,
    fill_price      REAL,
    stop_loss       REAL,
    take_profit     REAL,
    close_price     REAL,
    close_reason    TEXT,
    pnl_pips        REAL,
    pnl_money       REAL,
    plan_trigger    REAL,
    plan_stop       REAL,
    plan_target     REAL,
    fomak           TEXT,
    fopok           TEXT,
    -- As the broker reported it on the entry candle. Careful with the
    -- unit across history: measured against real fills, USDJPY reads in
    -- pips and EURUSD in points before September 2026, both in pips
    -- after. The real spread at the fills is 1.25 (USDJPY) and 1.05
    -- (EURUSD) pips.
    spread_at_entry REAL
);
"""

# How far each table has been filled. A derived copy that quietly stops
# updating is worse than no copy, so the watermark is data, not a guess.
STATE_SQL = """
CREATE TABLE IF NOT EXISTS sync_state (
    table_name  TEXT PRIMARY KEY,
    watermark   TEXT,
    rows        INTEGER NOT NULL DEFAULT 0,
    synced_at   TEXT NOT NULL,
    last_error  TEXT
);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (and create) the reporting database."""
    p = Path(path) if path else DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute(STATE_SQL)
    con.execute(TRADES_SQL)
    con.commit()
    return con


def watermark(con: sqlite3.Connection, table: str) -> str | None:
    row = con.execute(
        "SELECT watermark FROM sync_state WHERE table_name = ?", (table,)
    ).fetchone()
    return row["watermark"] if row else None


def set_state(
    con: sqlite3.Connection, table: str, mark: str | None,
    rows: int, error: str | None = None,
) -> None:
    con.execute(
        "INSERT OR REPLACE INTO sync_state (table_name, watermark, rows, synced_at, "
        "last_error) VALUES (?,?,?,?,?)",
        (table, mark, rows, datetime.now().astimezone().isoformat(), error),
    )


def status(con: sqlite3.Connection) -> list[dict[str, Any]]:
    """What is in here and how current it is — for the repair tool and the UI."""
    return [dict(r) for r in con.execute(
        "SELECT table_name, watermark, rows, synced_at, last_error "
        "FROM sync_state ORDER BY table_name"
    )]
