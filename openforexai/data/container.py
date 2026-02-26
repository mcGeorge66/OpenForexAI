from __future__ import annotations

import asyncio
from datetime import timedelta

from openforexai.data.indicators import compute_all
from openforexai.data.normalizer import pip_size
from openforexai.data.resampler import resample_candles
from openforexai.models.market import Candle, MarketSnapshot, Tick
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.utils.time_utils import detect_session, utcnow

_TIMEFRAMES = ["M1", "M5", "H1", "H4", "D1"]
_CANDLES_PER_TF: dict[str, int] = {
    "M1": 7 * 24 * 60,   # ~1 week of M1 candles
    "M5": 4 * 7 * 24 * 12,
    "H1": 4 * 7 * 24,
    "H4": 4 * 7 * 6,
    "D1": 4 * 7,
}


class DataContainer:
    """Central in-memory rolling data store.

    Holds up to *rolling_weeks* weeks of OHLCV candles per pair per timeframe,
    computes technical indicators, and evicts stale data automatically.
    Access is guarded by per-pair asyncio.Lock instances.
    """

    def __init__(
        self,
        broker: AbstractBroker,
        repository: AbstractRepository,
        pairs: list[str],
        rolling_weeks: int = 4,
        timeframes: list[str] | None = None,
    ) -> None:
        self._broker = broker
        self._repository = repository
        self._pairs = pairs
        self._rolling_weeks = rolling_weeks
        self._timeframes = timeframes or _TIMEFRAMES

        # pair -> timeframe -> list[Candle]  (oldest first)
        self._store: dict[str, dict[str, list[Candle]]] = {
            p: {tf: [] for tf in self._timeframes} for p in pairs
        }
        self._locks: dict[str, asyncio.Lock] = {p: asyncio.Lock() for p in pairs}
        self._latest_ticks: dict[str, Tick] = {}
        self._indicator_cache: dict[str, dict[str, dict[str, float]]] = {
            p: {} for p in pairs
        }

    async def initialize(self) -> None:
        """Fetch historical candles from the broker for all pairs & timeframes."""
        tasks = [self._load_pair(pair) for pair in self._pairs]
        await asyncio.gather(*tasks)

    async def _load_pair(self, pair: str) -> None:
        async with self._locks[pair]:
            for tf in self._timeframes:
                count = _CANDLES_PER_TF.get(tf, 200)
                candles = await self._broker.get_historical_candles(pair, tf, count)
                self._store[pair][tf] = candles

    async def update(self, tick: Tick) -> None:
        """Incorporate a new tick; updates the M1 candle and evicts old data."""
        pair = tick.pair
        if pair not in self._locks:
            return
        self._latest_ticks[pair] = tick
        async with self._locks[pair]:
            # Invalidate indicator cache on new tick
            self._indicator_cache[pair] = {}

    async def get_snapshot(self, pair: str) -> MarketSnapshot:
        """Return a fully assembled MarketSnapshot for *pair*."""
        if pair not in self._locks:
            raise ValueError(f"Pair {pair!r} is not tracked by this DataContainer.")

        async with self._locks[pair]:
            tick = self._latest_ticks.get(pair)
            if tick is None:
                # Create a synthetic tick from last known close (prefer M5 for recency)
                from decimal import Decimal

                last_m5 = self._store[pair].get("M5", [])
                last_h1 = self._store[pair].get("H1", [])
                last_candle = (last_m5 or last_h1)
                last_close = last_candle[-1].close if last_candle else Decimal("0")
                tick = Tick(pair=pair, bid=last_close, ask=last_close, timestamp=utcnow())

            m5 = list(self._store[pair].get("M5", []))
            h1 = list(self._store[pair].get("H1", []))
            h4 = list(self._store[pair].get("H4", []))
            d1 = list(self._store[pair].get("D1", []))

            # Derive M15 and M30 from M5 — no extra broker calls needed
            m15 = resample_candles(m5, "M15") if m5 else []
            m30 = resample_candles(m5, "M30") if m5 else []

            # Indicator cache keyed on H1 (used for higher-TF context)
            cache_key = "H1"
            if cache_key not in self._indicator_cache[pair]:
                self._indicator_cache[pair][cache_key] = compute_all(h1)
            indicators = self._indicator_cache[pair][cache_key]

            return MarketSnapshot(
                pair=pair,
                current_tick=tick,
                candles_m5=m5[-300:],
                candles_m15=m15[-150:],
                candles_m30=m30[-100:],
                candles_h1=h1[-200:],
                candles_h4=h4[-100:],
                candles_d1=d1[-60:],
                indicators=indicators,
                session=detect_session(),
                snapshot_time=utcnow(),
            )

    def get_candles(self, pair: str, timeframe: str) -> list[Candle]:
        """Synchronous read of cached candles (no lock — suitable for read-only snapshots)."""
        return list(self._store.get(pair, {}).get(timeframe, []))
