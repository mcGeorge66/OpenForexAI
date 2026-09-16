"""compute_fomak reads the stored key before it computes one.

The DataContainer already writes a key per closed candle. Recomputing it on
every question costs ~10 ms each and, worse, produces a second opinion where
there should be one answer — the whole reason the table exists.

What must hold:
  - a stored row is used, and the answer looks the same as a computed one
  - nothing is stored, and nothing is read, when the caller explicitly asks
    for the forming candle
  - a repository that is missing, old or slow means "compute it yourself",
    never "fail the analysis"
  - a freshly computed key is stamped the way the maintenance stamps it, so
    an anchor mid-candle and one at its close never make two rows
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from openforexai.tools.base import ToolContext
from openforexai.tools.market.compute_fomak import ComputeFomakTool

ANCHOR = "2026-07-01T12:03:00+00:00"
STORED = {
    "timestamp": "2026-07-01T12:00:00+00:00",
    "param_set": "M5-24-M30-14-50-a5e8feae-p2",
    "fomak": "3U331S",
    "fomak_text": "FOMAK 3U331S describes a market that is overall upwards (bullish).",
    "fopok": None,
    "fopok_text": None,
    "raw_values": '{"strength":2.1,"vola_ratio":0.94}',
    "computed_at": "2026-07-01T12:00:05+00:00",
}


class _Bus:
    """Answers repo_request; records what was asked and written."""

    def __init__(self, stored: dict | None, fail: bool = False) -> None:
        self.stored = stored
        self.fail = fail
        self.reads: list[dict] = []
        self.writes: list[dict] = []

    def register_response_future(self, key, future):
        self._future = future

    def cancel_response_future(self, key):
        pass

    async def publish(self, message, triggered_by=None):
        payload = message.payload
        op = payload.get("operation")
        if op == "get_market_key_at":
            self.reads.append(payload["args"])
            if self.fail:
                raise RuntimeError("repository unreachable")
            self._future.set_result({"result": self.stored})
        elif op == "save_market_keys":
            self.writes.append(payload["args"])
            self._future.set_result({"result": 1})
        else:
            self._future.set_result({"result": None})


def _context(bus) -> ToolContext:
    return ToolContext(agent_id="T", broker_name="OXS_T", pair="USDJPY", event_bus=bus)


def _args(**over) -> dict:
    base = {"timeframe": "M5", "lookback_candles": 24, "higher_timeframe": "M30",
            "anchor": ANCHOR}
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_a_stored_key_is_used() -> None:
    bus = _Bus(STORED)
    result = await ComputeFomakTool().execute(_args(), _context(bus))
    assert result["fomak"] == "3U331S"
    assert result["from_store"] is True
    assert bus.reads and bus.reads[0]["param_set"].endswith("-p2")
    # The row's own timestamp is reported, not the anchor that was asked for.
    assert result["anchor"] == STORED["timestamp"]


@pytest.mark.asyncio
async def test_stored_answer_carries_raw_values_and_text() -> None:
    bus = _Bus(STORED)
    result = await ComputeFomakTool().execute(
        _args(include_raw_values=True, include_explanation=True), _context(bus))
    assert result["raw_values"]["strength"] == 2.1
    assert "bullish" in result["explanation"]


@pytest.mark.asyncio
async def test_the_forming_candle_never_touches_the_store() -> None:
    """The stored value is the closed-candle one. Asking for the bar in
    progress must neither read it nor overwrite it with something else."""
    bus = _Bus(STORED)
    result = await ComputeFomakTool().execute(
        _args(include_forming_candle=True), _context(bus))
    assert bus.reads == []
    assert bus.writes == []
    assert result.get("from_store") is not True


@pytest.mark.asyncio
async def test_an_unreachable_repository_is_not_an_error() -> None:
    """Falling back costs time and nothing else — the value is reproducible."""
    bus = _Bus(None, fail=True)
    from openforexai.tools.market.compute_fomak import _stored_key

    assert await _stored_key(_context(bus), "USDJPY", "M5", "p", ANCHOR) is None


@pytest.mark.asyncio
async def test_a_row_without_a_code_is_not_treated_as_a_hit() -> None:
    bus = _Bus({**STORED, "fomak": ""})
    from openforexai.tools.market.compute_fomak import _stored_key

    assert await _stored_key(_context(bus), "USDJPY", "M5", "p", ANCHOR) is None


@pytest.mark.asyncio
async def test_a_fresh_key_is_stamped_at_the_candle_close() -> None:
    """Same stamp the maintenance uses, so a mid-candle anchor and one at the
    close do not create two rows for the same market."""
    bus = _Bus(None)
    from openforexai.tools.market.compute_fomak import _store_key

    await _store_key(
        _context(bus), "USDJPY", "M5", "params",
        "2026-07-01T11:55:00+00:00", {"fomak": "3U331S", "raw_values": {}},
    )
    assert bus.writes, "nothing was stored"
    row = bus.writes[0]["rows"][0]
    assert row[0] == "2026-07-01T12:00:00+00:00"   # 11:55 opened, 12:00 closed
    assert row[2] == "3U331S"


@pytest.mark.asyncio
async def test_storing_never_raises_into_the_analysis() -> None:
    class _Broken(_Bus):
        async def publish(self, message, triggered_by=None):
            raise RuntimeError("disk on fire")

    from openforexai.tools.market.compute_fomak import _store_key

    await _store_key(_context(_Broken(None)), "USDJPY", "M5", "p",
                     "2026-07-01T11:55:00+00:00", {"fomak": "3U331S"})
