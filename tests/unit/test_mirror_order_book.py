"""Das Orderbuch im Simulator: der Spiegel, zum Ankerzeitpunkt.

Zwei Bloecke des Live-Profils lesen das Orderbuch. Im Simulator war das
Werkzeug gesperrt, also fehlten sie dort — der simulierte Snapshot war ein
anderer als der echte. Jetzt liest es den Spiegel, und zwar als-ob: was zum
Anker noch nicht geschehen war, darf nicht sichtbar sein. Sonst weiss eine
Simulation des letzten Dienstags, wie der Trade ausgegangen ist.
"""
from __future__ import annotations

import sqlite3

import pytest

from openforexai.data import reporting_db as rdb
from openforexai.data.reporting_reader import ReportingReader, ReportingUnavailable

# opened_at kommt vom Broker mit +03:00, requested_at wird als UTC geschrieben.
# Genau diese Mischung muss die Als-ob-Grenze ueberstehen.
TRADES = [
    # (id, pair, richtung, requested_at, opened_at, closed_at, pnl_money)
    ("A1", "USDJPY", "BUY",  "2026-09-16T09:00:00+00:00", "2026-09-16T12:00:00+03:00",
     "2026-09-16T15:00:00+03:00", 42.0),      # 09:00 .. 12:00 UTC
    ("A2", "USDJPY", "SELL", "2026-09-16T13:00:00+00:00", "2026-09-16T16:00:00+03:00",
     None, None),                              # ab 13:00 UTC offen geblieben
    ("A3", "USDJPY", "BUY",  "2026-09-16T20:00:00+00:00", "2026-09-16T23:00:00+03:00",
     "2026-09-17T01:00:00+03:00", -7.0),       # erst ab 20:00 UTC
    ("B1", "EURUSD", "BUY",  "2026-09-16T09:00:00+00:00", "2026-09-16T12:00:00+03:00",
     None, None),                              # anderes Paar
]


@pytest.fixture()
def spiegel(tmp_path):
    pfad = tmp_path / "rep.db"
    con = sqlite3.connect(str(pfad))
    con.execute(rdb.TRADES_SQL if hasattr(rdb, "TRADES_SQL") else """
        CREATE TABLE trades (
            broker_order_id TEXT PRIMARY KEY, pair TEXT, direction TEXT,
            requested_at TEXT, opened_at TEXT, closed_at TEXT, units REAL,
            fill_price REAL, stop_loss REAL, take_profit REAL, close_price REAL,
            close_reason TEXT, pnl_pips REAL, pnl_money REAL, plan_trigger REAL,
            plan_stop REAL, plan_target REAL, fomak TEXT, fopok TEXT,
            spread_at_entry REAL)""")
    for oid, pair, richtung, req, auf, zu, pnl in TRADES:
        con.execute(
            "INSERT INTO trades (broker_order_id, pair, direction, requested_at, opened_at,"
            " closed_at, pnl_money, close_reason) VALUES (?,?,?,?,?,?,?,?)",
            (oid, pair, richtung, req, auf, zu, pnl, "TP" if zu else None))
    con.commit()
    con.close()
    return ReportingReader(pfad)


def _ids(rows):
    return sorted(str(r["broker_order_id"]) for r in rows)


def test_open_means_open_back_then(spiegel) -> None:
    """14:00 UTC: A1 ist laengst zu, A2 laeuft, A3 gibt es noch nicht."""
    assert _ids(spiegel.get_trades("USDJPY", status="open",
                                   as_of="2026-09-16T14:00:00+00:00")) == ["A2"]


def test_a_trade_still_running_hides_its_ending(spiegel) -> None:
    """Sonst weiss die Simulation, wie es ausgeht."""
    (t,) = spiegel.get_trades("USDJPY", status="open", as_of="2026-09-16T10:00:00+00:00")
    assert str(t["broker_order_id"]) == "A1"
    assert t["status"] == "OPEN"
    assert t["closed_at"] is None, "das Ende lag in der Zukunft"
    assert t["pnl_account_currency"] is None, "das Ergebnis lag in der Zukunft"


def test_a_trade_from_later_does_not_exist_yet(spiegel) -> None:
    alle = spiegel.get_trades("USDJPY", status="all", as_of="2026-09-16T14:00:00+00:00")
    assert "A3" not in _ids(alle)


def test_closed_means_closed_by_then(spiegel) -> None:
    zu = spiegel.get_trades("USDJPY", status="closed", as_of="2026-09-16T14:00:00+00:00")
    assert _ids(zu) == ["A1"]
    assert zu[0]["pnl_account_currency"] == 42.0, "abgeschlossen, also sichtbar"


def test_the_offset_mix_is_compared_as_time_not_text(spiegel) -> None:
    """A1 schliesst '15:00:00+03:00' = 12:00 UTC. Als Text verglichen laege
    das hinter '2026-09-16T13:00:00+00:00' und der Trade schiene noch offen."""
    offen = spiegel.get_trades("USDJPY", status="open", as_of="2026-09-16T13:00:00+00:00")
    assert "A1" not in _ids(offen), "um 13:00 UTC war A1 seit einer Stunde geschlossen"


def test_other_pairs_stay_out(spiegel) -> None:
    assert "B1" not in _ids(spiegel.get_trades("USDJPY", status="all"))


def test_without_an_anchor_open_means_open_now(spiegel) -> None:
    assert _ids(spiegel.get_trades("USDJPY", status="open")) == ["A2"]


def test_a_mirror_without_trades_says_so(tmp_path) -> None:
    pfad = tmp_path / "leer.db"
    sqlite3.connect(str(pfad)).close()
    with pytest.raises(ReportingUnavailable) as exc:
        ReportingReader(pfad).get_trades("USDJPY")
    assert "reporting_db.py --sync" in str(exc.value)


@pytest.mark.asyncio
async def test_a_state_the_mirror_cannot_answer_raises(spiegel) -> None:
    """'pending' beantwortet der Spiegel nicht. Eine leere Liste hiesse
    'gab es nicht' statt 'weiss ich nicht'."""
    from openforexai.tools.base import ToolContext
    from openforexai.tools.orderbook.get_order_book import GetOrderBookTool

    ctx = ToolContext(agent_id="T", broker_name="OXS_T", pair="USDJPY",
                      data_source="reporting")
    with pytest.raises(RuntimeError) as exc:
        await GetOrderBookTool().execute({"status_filter": "pending"}, ctx)
    assert "cannot be answered from the reporting mirror" in str(exc.value)


@pytest.mark.asyncio
async def test_the_simulation_never_reaches_the_repository(monkeypatch, spiegel) -> None:
    """Der eigentliche Punkt: kein Weg zurueck in die Produktion."""
    from openforexai.tools import base
    from openforexai.tools.base import ToolContext
    from openforexai.tools.orderbook import get_order_book as modul

    async def verboten(*a, **k):
        raise AssertionError("repo_request im Simulator aufgerufen")

    monkeypatch.setattr(modul, "repo_request", verboten, raising=False)
    monkeypatch.setattr(base, "repo_request", verboten, raising=False)
    # Das Werkzeug legt den Leser selbst an; ueber die Vorgabe zeigt er auf den Test-Spiegel.
    monkeypatch.setattr("openforexai.data.reporting_db.DEFAULT_PATH", spiegel._path)

    ctx = ToolContext(agent_id="T", broker_name="OXS_T", pair="USDJPY",
                      data_source="reporting", as_of="2026-09-16T14:00:00+00:00")
    rows = await modul.GetOrderBookTool().execute({"status_filter": "open"}, ctx)
    assert _ids(rows) == ["A2"]
