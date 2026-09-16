"""The DataContainer keeps the key table current, and agrees with the backfill.

Two implementations of the same computation is how the market key went wrong
twice in one evening — a one-candle shift and a wrong higher-timeframe bar
count, both invisible until a spot check caught them. The live maintenance and
the backfill script therefore share `fopok_from_levels` and `row_for`, and
this file pins the properties that must hold whichever writes the row.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from openforexai.data.container import DataContainer
from openforexai.data.market_keys import (
    DEFAULT_SETTINGS,
    FOPOK_MIN_BARS,
    fopok_from_levels,
    keys_table,
    param_set,
)
from openforexai.models.market import Candle


def _candles(count: int, start: datetime | None = None) -> list[Candle]:
    """A gently rising series, oldest first, all of them closed."""
    base = start or (datetime.now(UTC) - timedelta(minutes=5 * (count + 1)))
    out = []
    for i in range(count):
        price = Decimal("155.000") + Decimal(i) * Decimal("0.004")
        out.append(Candle(
            timestamp=base + timedelta(minutes=5 * i),
            open=price, high=price + Decimal("0.020"),
            low=price - Decimal("0.020"), close=price,
            tick_volume=100, spread=Decimal("1.1"), timeframe="M5",
        ))
    return out


class _Store:
    """Just enough store for the maintenance path."""

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles
        self.saved: list[tuple] = []

    async def get_candles(self, broker_name, pair, timeframe, limit=500, start=None):
        return list(reversed(self._candles[-limit:]))   # newest first, as the real one

    async def get_market_keys(self, broker_name, pair, timeframe, param_set,
                              start=None, end=None, limit=None):
        return [{"timestamp": r[0]} for r in self.saved]

    async def save_market_keys(self, broker_name, pair, timeframe, rows):
        self.saved.extend(rows)
        return len(rows)


def _container(store: _Store, settings=None) -> DataContainer:
    return DataContainer(store=store, market_key_settings=settings)


@pytest.mark.asyncio
async def test_writes_a_row_for_closed_candles() -> None:
    store = _Store(_candles(400))
    await _container(store)._maintain_market_keys("OXS_T", "USDJPY")
    assert store.saved, "no key written at all"
    # timestamp, param_set, fomak are the first three columns
    assert all(len(r[2]) == 6 for r in store.saved), "a FOMAK has six characters"


@pytest.mark.asyncio
async def test_is_bounded_per_call() -> None:
    """The container's message loop is sequential — one call must not try to
    fill months of backlog and stall candle intake."""
    store = _Store(_candles(600))
    c = _container(store)
    await c._maintain_market_keys("OXS_T", "USDJPY")
    assert len(store.saved) <= c._MARKET_KEY_MAX_PER_CALL


@pytest.mark.asyncio
async def test_does_not_rewrite_what_is_already_there() -> None:
    store = _Store(_candles(400))
    c = _container(store)
    await c._maintain_market_keys("OXS_T", "USDJPY")
    first = len(store.saved)
    await c._maintain_market_keys("OXS_T", "USDJPY")
    assert len(store.saved) == first, "the same candle was written twice"


@pytest.mark.asyncio
async def test_the_forming_candle_gets_no_key() -> None:
    """A key for a candle still being built would change with the next tick."""
    now = datetime.now(UTC)
    candles = _candles(400, start=now - timedelta(minutes=5 * 399))
    assert candles[-1].timestamp + timedelta(minutes=5) > now, "last candle should be open"
    store = _Store(candles)
    await _container(store)._maintain_market_keys("OXS_T", "USDJPY")
    newest_written = max(r[0] for r in store.saved)
    assert newest_written <= candles[-1].timestamp.isoformat()


@pytest.mark.asyncio
async def test_empty_settings_switch_it_off() -> None:
    store = _Store(_candles(400))
    await _container(store, settings=[])._maintain_market_keys("OXS_T", "USDJPY")
    assert store.saved == []


@pytest.mark.asyncio
async def test_a_failing_store_never_breaks_candle_intake() -> None:
    """Candle storage must not depend on a derived value."""
    class _Broken(_Store):
        async def save_market_keys(self, *a, **k):
            raise RuntimeError("disk on fire")

    store = _Broken(_candles(400))
    # Must not raise.
    await _container(store)._maintain_market_keys("OXS_T", "USDJPY")


@pytest.mark.asyncio
async def test_a_store_without_the_method_is_tolerated() -> None:
    """An older repository implementation must not crash the container."""
    class _Old:
        async def get_candles(self, *a, **k):
            return []

    await _container(_Old())._maintain_market_keys("OXS_T", "USDJPY")


def test_too_little_history_gives_a_reason_not_a_blank() -> None:
    code, raw, reason = fopok_from_levels([], [], 155.0, DEFAULT_SETTINGS)
    assert code is None and raw is None
    assert str(FOPOK_MIN_BARS) in reason


def test_table_and_parameter_set_match_the_backfill() -> None:
    """Both writers must address the same rows."""
    assert keys_table("OXS_T", "USDJPY", "M5") == "OXS_T_USDJPY_M5_keys"
    assert param_set(
        timeframe=DEFAULT_SETTINGS["timeframe"],
        lookback_candles=DEFAULT_SETTINGS["lookback_candles"],
        higher_timeframe=DEFAULT_SETTINGS["higher_timeframe"],
    ) == "M5-24-M30-14-50-a5e8feae-p2"
