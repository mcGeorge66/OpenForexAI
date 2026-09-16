"""The bar currently being built must not reach a stored result.

A forming candle grows tick by tick, so a window that contains it answers the
same moment differently depending on when it is asked — and differently again
once the bar closed and the row was overwritten with its final values.

Measured on production data: of 103 trades whose FOMAK was stored at decision
time, the same tool with the same anchor and the same code reproduces only 62
today. Not a version difference (matches and mismatches span the same days),
and not a window-edge offset (shifting the anchor by one candle makes it
worse). The forming candle is the remaining explanation, and the size of the
hole it leaves is not small: an M5 bar four minutes old carries ~7% of a
finished bar's volume, and the FOMAK also reads a higher timeframe, where the
bar in progress is typically half missing.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from openforexai.tools.base import ToolContext, _drop_forming_candle, fetch_candles


def _candles(last_open: datetime, count: int = 3, minutes: int = 5) -> list[dict]:
    """`count` candles, the last one opening at *last_open*."""
    return [
        {"timestamp": (last_open - timedelta(minutes=minutes * i)).isoformat(),
         "close": str(100 + count - i)}
        for i in reversed(range(count))
    ]


def test_forming_candle_is_dropped_live() -> None:
    now = datetime.now(UTC)
    opened = now - timedelta(minutes=2)          # M5 bar, 3 minutes still to run
    candles = _candles(opened)
    assert len(_drop_forming_candle(candles, "M5", None)) == len(candles) - 1


def test_closed_candle_is_kept_live() -> None:
    now = datetime.now(UTC)
    opened = now - timedelta(minutes=7)          # M5 bar, ended 2 minutes ago
    candles = _candles(opened)
    assert _drop_forming_candle(candles, "M5", None) == candles


def test_anchor_decides_not_now() -> None:
    """A replay must drop the bar that was forming BACK THEN, not today."""
    opened = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    candles = _candles(opened)
    anchor_mid = datetime(2026, 7, 1, 12, 3, tzinfo=UTC).isoformat()   # still running
    anchor_after = datetime(2026, 7, 1, 12, 5, tzinfo=UTC).isoformat()  # just closed
    assert len(_drop_forming_candle(candles, "M5", anchor_mid)) == len(candles) - 1
    assert _drop_forming_candle(candles, "M5", anchor_after) == candles


@pytest.mark.parametrize(("timeframe", "minutes"), [("M15", 15), ("M30", 30), ("H1", 60)])
def test_higher_timeframes_use_their_own_period(timeframe: str, minutes: int) -> None:
    """The higher timeframe is where the hole is biggest — an H1 bar in progress
    is typically three quarters missing, and the FOMAK's alignment character
    reads exactly that bar."""
    opened = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    candles = _candles(opened, minutes=minutes)
    mid = (opened + timedelta(minutes=minutes - 1)).isoformat()
    done = (opened + timedelta(minutes=minutes)).isoformat()
    assert len(_drop_forming_candle(candles, timeframe, mid)) == len(candles) - 1
    assert _drop_forming_candle(candles, timeframe, done) == candles


def test_unknown_timeframe_changes_nothing() -> None:
    candles = _candles(datetime.now(UTC))
    assert _drop_forming_candle(candles, "W1", None) == candles


def test_empty_list_survives() -> None:
    assert _drop_forming_candle([], "M5", None) == []


class _Bus:
    def __init__(self, candles: list[dict]) -> None:
        self.candles = candles
        self.payloads: list[dict] = []

    def register_response_future(self, key, future):
        self._future = future

    def cancel_response_future(self, key):
        pass

    async def publish(self, message, triggered_by=None):
        self.payloads.append(dict(message.payload))
        limit = int(message.payload["limit"])
        self._future.set_result({"candles": self.candles[-limit:]})


@pytest.mark.asyncio
async def test_caller_still_gets_the_full_count() -> None:
    """Dropping one must not silently shorten the window — one extra is fetched."""
    now = datetime.now(UTC)
    bus = _Bus(_candles(now - timedelta(minutes=2), count=20))
    ctx = ToolContext(agent_id="T", broker_name="OXS_T", pair="USDJPY", event_bus=bus)
    result = await fetch_candles(ctx, "M5", 10)
    assert bus.payloads[0]["limit"] == 11
    assert len(result) == 10


@pytest.mark.asyncio
async def test_include_forming_opts_back_in() -> None:
    """The on-the-fly case: look at the bar in progress, never store the result."""
    now = datetime.now(UTC)
    bus = _Bus(_candles(now - timedelta(minutes=2), count=20))
    ctx = ToolContext(agent_id="T", broker_name="OXS_T", pair="USDJPY", event_bus=bus)
    result = await fetch_candles(ctx, "M5", 10, include_forming=True)
    assert bus.payloads[0]["limit"] == 10
    # The newest candle is the one still being built, and it is present.
    assert result[-1]["timestamp"] == bus.candles[-1]["timestamp"]
