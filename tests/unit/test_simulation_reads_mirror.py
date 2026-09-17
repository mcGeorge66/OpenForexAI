"""The simulation reads the reporting mirror, and only that.

A run that can quietly end up on live data produces numbers nobody can place
afterwards. So the source travels on the ToolContext — the same decision as
the time anchor, for the same reason: what lives in tool arguments has to be
known by every tool individually, and one of them forgets.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openforexai.data.reporting_reader import ReportingReader, ReportingUnavailable
from openforexai.tools.base import ToolContext, fetch_candles


class _Bus:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def register_response_future(self, key, future):
        self._future = future

    def cancel_response_future(self, key):
        pass

    async def publish(self, message, triggered_by=None):
        self.payloads.append(dict(message.payload))
        self._future.set_result({"candles": [
            {"timestamp": "2026-07-01T11:55:00+00:00", "close": "155.0"},
        ]})


def _ctx(bus, source=None) -> ToolContext:
    return ToolContext(agent_id="T", broker_name="OXS_T", pair="USDJPY",
                       event_bus=bus, data_source=source)


@pytest.mark.asyncio
async def test_the_source_reaches_the_request() -> None:
    bus = _Bus()
    await fetch_candles(_ctx(bus, "reporting"), "M5", 5)
    assert bus.payloads[0]["source"] == "reporting"


@pytest.mark.asyncio
async def test_live_sends_no_source_at_all() -> None:
    """Production must look exactly as it did before."""
    bus = _Bus()
    await fetch_candles(_ctx(bus), "M5", 5)
    assert "source" not in bus.payloads[0]


def test_a_missing_mirror_raises_instead_of_falling_back(tmp_path) -> None:
    """The fallback is the dangerous part: a study half on one database and
    half on another cannot be told from a good one afterwards."""
    reader = ReportingReader(tmp_path / "does-not-exist.db")
    with pytest.raises(ReportingUnavailable) as exc:
        reader.get_candles("OXS_T", "USDJPY", "M5")
    assert "reporting_db.py --sync" in str(exc.value), "the message must say how to fix it"


def test_a_pair_without_data_raises_too(tmp_path) -> None:
    import sqlite3
    from openforexai.data import reporting_db as rdb

    path = tmp_path / "rep.db"
    con = sqlite3.connect(str(path))
    con.execute(rdb.STATE_SQL)
    con.commit()
    con.close()
    with pytest.raises(ReportingUnavailable):
        ReportingReader(path).get_candles("OXS_T", "USDJPY", "M5")


def test_reads_the_materialised_timeframe(tmp_path) -> None:
    """H1 comes out of the H1 table — not aggregated from M5 on every call.
    That is what makes a sweep affordable."""
    import sqlite3
    from openforexai.data import reporting_db as rdb

    path = tmp_path / "rep.db"
    con = sqlite3.connect(str(path))
    table = rdb.table_name("OXS_T", "USDJPY", "H1")
    con.execute(rdb.CANDLE_SQL.format(table=table))
    con.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
        [(f"2026-07-01T{h:02d}:00:00+00:00", "155.0", "155.5", "154.5", "155.2", 900, "1.1")
         for h in range(8, 14)],
    )
    con.commit()
    con.close()

    got = ReportingReader(path).get_candles("OXS_T", "USDJPY", "H1", limit=3)
    assert len(got) == 3
    assert got[0].timestamp < got[-1].timestamp, "oldest first, like production"
    assert got[-1].timestamp == datetime(2026, 7, 1, 13, tzinfo=UTC)


def test_the_anchor_means_as_of_here_too(tmp_path) -> None:
    import sqlite3
    from openforexai.data import reporting_db as rdb

    path = tmp_path / "rep.db"
    con = sqlite3.connect(str(path))
    table = rdb.table_name("OXS_T", "USDJPY", "M5")
    con.execute(rdb.CANDLE_SQL.format(table=table))
    con.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
        [(f"2026-07-01T12:{m:02d}:00+00:00", "155.0", "155.1", "154.9", "155.0", 100, "1.1")
         for m in range(0, 60, 5)],
    )
    con.commit()
    con.close()

    got = ReportingReader(path).get_candles(
        "OXS_T", "USDJPY", "M5", limit=100, start="2026-07-01T12:20:00+00:00")
    assert got[-1].timestamp == datetime(2026, 7, 1, 12, 20, tzinfo=UTC)
    assert all(c.timestamp <= got[-1].timestamp for c in got)


def test_null_candles_are_dropped_as_in_production(tmp_path) -> None:
    """Gap placeholders are removed on the production read too — a simulation
    must see the same series, not a longer one."""
    import sqlite3
    from openforexai.data import reporting_db as rdb

    path = tmp_path / "rep.db"
    con = sqlite3.connect(str(path))
    table = rdb.table_name("OXS_T", "USDJPY", "M5")
    con.execute(rdb.CANDLE_SQL.format(table=table))
    con.executemany(
        f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
        [("2026-07-01T12:00:00+00:00", "155.0", "155.1", "154.9", "155.0", 100, "1.1"),
         ("2026-07-01T12:05:00+00:00", "0", "0", "0", "0", 0, "0"),
         ("2026-07-01T12:10:00+00:00", "155.0", "155.1", "154.9", "155.0", 100, "1.1")],
    )
    con.commit()
    con.close()

    got = ReportingReader(path).get_candles("OXS_T", "USDJPY", "M5")
    assert len(got) == 2
