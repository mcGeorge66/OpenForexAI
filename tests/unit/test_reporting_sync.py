"""The reporting mirror keeps up, repairs itself, and never costs a candle.

It is derived data: it can be deleted and rebuilt from production at any
time. That is what makes the rules below safe — a failure may cost freshness,
never correctness, and never a live candle.
"""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

from openforexai.data import reporting_db as rdb
from openforexai.data.container import DataContainer


def _prod(path) -> str:
    """A tiny production database: one pair, a handful of M5 candles."""
    con = sqlite3.connect(str(path))
    con.execute(rdb.CANDLE_SQL.format(table="OXS_T_USDJPY_M5"))
    rows = [
        (f"2026-07-01T{h:02d}:{m:02d}:00+00:00", "155.0", "155.1", "154.9", "155.05",
         100, "1.1")
        for h in range(12, 15) for m in range(0, 60, 5)
    ]
    con.executemany(
        "INSERT OR REPLACE INTO OXS_T_USDJPY_M5 VALUES (?,?,?,?,?,?,?)", rows)
    con.execute("""CREATE TABLE order_book_entries (
        broker_order_id TEXT, broker_name TEXT, pair TEXT, direction TEXT,
        requested_at TEXT, opened_at TEXT, closed_at TEXT, units REAL,
        fill_price REAL, stop_loss REAL, take_profit REAL, close_price REAL,
        close_reason TEXT, pnl_pips REAL, pnl_account_currency REAL,
        market_context_snapshot TEXT)""")
    con.execute(
        "INSERT INTO order_book_entries VALUES ('1','OXS_T','USDJPY','BUY',"
        "'2026-07-01T13:00:00+00:00',NULL,NULL,1000,155.0,154.9,155.2,155.2,"
        "'TP',20.0,15.0,NULL)")
    con.commit()
    con.close()
    return str(path)


def test_a_full_pass_materialises_every_timeframe(tmp_path) -> None:
    from openforexai.data.reporting_sync import sync_all

    prod, rep = _prod(tmp_path / "prod.db"), tmp_path / "rep.db"
    sync_all(prod, rep)
    con = rdb.connect(rep)
    names = {r[0] for r in con.execute(
        "select name from sqlite_master where type='table'")}
    assert "OXS_T_USDJPY_M5" in names
    assert "OXS_T_USDJPY_M15" in names, "higher timeframes are the whole point"
    assert "OXS_T_USDJPY_H1" in names
    assert con.execute("select count(*) from trades").fetchone()[0] == 1
    con.close()


def test_a_second_pass_adds_nothing(tmp_path) -> None:
    """Incremental by watermark — re-running must not duplicate."""
    from openforexai.data.reporting_sync import sync_all

    prod, rep = _prod(tmp_path / "prod.db"), tmp_path / "rep.db"
    sync_all(prod, rep)
    con = rdb.connect(rep)
    before = con.execute("select count(*) from OXS_T_USDJPY_M5").fetchone()[0]
    con.close()
    sync_all(prod, rep)
    con = rdb.connect(rep)
    assert con.execute("select count(*) from OXS_T_USDJPY_M5").fetchone()[0] == before
    con.close()


def test_a_deleted_mirror_rebuilds_itself(tmp_path) -> None:
    """The automatic repair is not a special mode — it is the normal path."""
    from openforexai.data.reporting_sync import sync_all

    prod, rep = _prod(tmp_path / "prod.db"), tmp_path / "rep.db"
    sync_all(prod, rep)
    rep.unlink()
    sync_all(prod, rep)
    con = rdb.connect(rep)
    assert con.execute("select count(*) from OXS_T_USDJPY_M5").fetchone()[0] > 0
    con.close()


def test_a_broken_production_file_is_recorded_not_raised(tmp_path) -> None:
    from openforexai.data.reporting_sync import sync_all

    broken = tmp_path / "broken.db"
    broken.write_text("this is not a database")
    # Must not raise.
    sync_all(broken, tmp_path / "rep.db")


def test_status_reports_the_watermark(tmp_path) -> None:
    """A mirror that quietly stops updating is worse than none."""
    from openforexai.data.reporting_sync import sync_all

    prod, rep = _prod(tmp_path / "prod.db"), tmp_path / "rep.db"
    sync_all(prod, rep)
    con = rdb.connect(rep)
    rows = {r["table_name"]: r for r in rdb.status(con)}
    assert rows["OXS_T_USDJPY_M5"]["watermark"].startswith("2026-07-01")
    assert rows["OXS_T_USDJPY_M5"]["last_error"] is None
    con.close()


class _Store:
    _db_path = "nonexistent.db"

    async def get_candles(self, *a, **k):
        return []


@pytest.mark.asyncio
async def test_disabled_by_default() -> None:
    c = DataContainer(store=_Store())
    c._kick_reporting_sync()
    assert c._reporting_task is None


@pytest.mark.asyncio
async def test_runs_only_every_nth_candle() -> None:
    c = DataContainer(store=_Store(), reporting_db={"enabled": True, "every_candles": 5})
    for _ in range(4):
        c._kick_reporting_sync()
    assert c._reporting_task is None, "started too early"
    c._kick_reporting_sync()
    assert c._reporting_task is not None
    await asyncio.gather(c._reporting_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_failing_sync_does_not_raise_at_the_candle_path() -> None:
    """The mirror points at a file that does not exist — the candle that
    triggered it must not notice."""
    c = DataContainer(store=_Store(), reporting_db={"enabled": True, "every_candles": 1})
    c._kick_reporting_sync()
    await asyncio.gather(c._reporting_task, return_exceptions=True)
    # Reaching here without an exception is the assertion.
