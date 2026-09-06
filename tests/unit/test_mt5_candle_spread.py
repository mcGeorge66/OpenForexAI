from __future__ import annotations

from datetime import timedelta, timezone

import numpy as np
import pytest

from openforexai.adapters.brokers.mt5 import MT5Broker


def _make_broker() -> MT5Broker:
    broker = object.__new__(MT5Broker)
    broker._short_name = "OXS_T"
    broker._api_timeout_seconds = 5.0
    broker._broker_tz = timezone(timedelta(hours=3))
    return broker


def _make_rates(spread_points: list[int]) -> np.ndarray:
    dtype = np.dtype([
        ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
        ("close", "f8"), ("tick_volume", "i8"), ("spread", "i8"),
    ])
    rows = [
        (1_700_000_000 + i * 300, 1.1000, 1.1010, 1.0990, 1.1005, 100, sp)
        for i, sp in enumerate(spread_points)
    ]
    return np.array(rows, dtype=dtype)


@pytest.mark.asyncio
async def test_historical_candles_convert_mt5_points_to_pips() -> None:
    """MT5's own 'spread' field is in points, not pips (10 points = 1 pip for the
    5-/3-digit quoting all traded pairs use here) — Candle.spread is documented as
    pips, so get_historical_m5_candles must divide by 10, not copy the raw value."""
    broker = _make_broker()
    broker._mt5 = type("_FakeMT5", (), {
        "TIMEFRAME_M5": 5,
        "copy_rates_from_pos": staticmethod(lambda *a, **k: _make_rates([10, 21, 0])),
    })()

    candles = await broker.get_historical_m5_candles("EURUSD", count=3)

    assert [float(c.spread) for c in candles] == [1.0, 2.1, 0.0]


@pytest.mark.asyncio
async def test_historical_candles_missing_spread_field_defaults_to_zero() -> None:
    broker = _make_broker()
    dtype = np.dtype([
        ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
        ("close", "f8"), ("tick_volume", "i8"),
    ])
    rates = np.array([(1_700_000_000, 1.1, 1.1, 1.1, 1.1, 100)], dtype=dtype)
    broker._mt5 = type("_FakeMT5", (), {
        "TIMEFRAME_M5": 5,
        "copy_rates_from_pos": staticmethod(lambda *a, **k: rates),
    })()

    candles = await broker.get_historical_m5_candles("EURUSD", count=1)

    assert float(candles[0].spread) == 0.0
