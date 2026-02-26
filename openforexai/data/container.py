from __future__ import annotations

import asyncio
from decimal import Decimal

from openforexai.data.indicators import compute_all
from openforexai.data.normalizer import pip_size
from openforexai.data.resampler import resample_candles
from openforexai.models.market import Candle, MarketSnapshot, Tick
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.utils.time_utils import detect_session, utcnow

# Only M5 is fetched from the broker.
# All other timeframes are derived via the resampler — no extra API traffic.
_SOURCE_TF = "M5"
_M5_COUNT = 4 * 7 * 24 * 12  # ~4 weeks of M5 bars (≈ 8 064 candles)

# Snapshot window sizes per derived timeframe
_SNAPSHOT_LIMITS: dict[str, int] = {
    "M5":  300,
    "M15": 150,
    "M30": 100,
    "H1":  200,
    "H4":  100,
    "D1":   60,
}


class DataContainer:
    """Central in-memory rolling data store.

    Only M5 candles are fetched from the broker.  All higher timeframes
    (M15, M30, H1, H4, D1) are derived on-demand via the resampler.

    Access is guarded by per-pair asyncio.Lock instances.
    """

    def __init__(
        self,
        broker: AbstractBroker,
        repository: AbstractRepository,
        pairs: list[str],
        rolling_weeks: int = 4,
        timeframes: list[str] | None = None,  # kept for API compat, ignored
    ) -> None:
        self._broker = broker
        self._repository = repository
        self._pairs = pairs
        self._rolling_weeks = rolling_weeks

        # pair → list[Candle M5]  (oldest first)
        self._m5_store: dict[str, list[Candle]] = {p: [] for p in pairs}
        self._locks: dict[str, asyncio.Lock] = {p: asyncio.Lock() for p in pairs}
        self._latest_ticks: dict[str, Tick] = {}
        # pair → tf → computed indicators
        self._indicator_cache: dict[str, dict[str, dict[str, float]]] = {
            p: {} for p in pairs
        }

    async def initialize(self) -> None:
        """Fetch M5 history from the broker for all pairs."""
        tasks = [self._load_pair(pair) for pair in self._pairs]
        await asyncio.gather(*tasks)

    async def _load_pair(self, pair: str) -> None:
        async with self._locks[pair]:
            candles = await self._broker.get_historical_candles(
                pair, _SOURCE_TF, _M5_COUNT
            )
            self._m5_store[pair] = candles

    async def update(self, tick: Tick) -> None:
        """Incorporate a new tick; invalidates the indicator cache."""
        pair = tick.pair
        if pair not in self._locks:
            return
        self._latest_ticks[pair] = tick
        async with self._locks[pair]:
            self._indicator_cache[pair] = {}

    # ── Candle access (synchronous, no lock — read-only snapshots) ────────────

    def get_candles(self, pair: str, timeframe: str) -> list[Candle]:
        """Return candles for *pair* at *timeframe*, deriving from M5 if needed.

        This is the single entry-point used by all agents and tools.
        """
        m5 = list(self._m5_store.get(pair, []))
        if timeframe == "M5":
            return m5
        if timeframe in ("M15", "M30", "H1", "H4", "D1"):
            return resample_candles(m5, timeframe)
        # Unknown timeframe — return empty rather than crash
        return []

    # ── Snapshot assembly (async, per-pair lock) ──────────────────────────────

    async def get_snapshot(self, pair: str) -> MarketSnapshot:
        """Return a fully assembled MarketSnapshot for *pair*."""
        if pair not in self._locks:
            raise ValueError(f"Pair {pair!r} is not tracked by this DataContainer.")

        async with self._locks[pair]:
            tick = self._latest_ticks.get(pair)
            if tick is None:
                m5 = self._m5_store.get(pair, [])
                last_close = m5[-1].close if m5 else Decimal("0")
                tick = Tick(pair=pair, bid=last_close, ask=last_close, timestamp=utcnow())

            m5 = list(self._m5_store.get(pair, []))

        # Derive all higher timeframes from M5 (outside the lock — pure computation)
        m15 = resample_candles(m5, "M15") if m5 else []
        m30 = resample_candles(m5, "M30") if m5 else []
        h1  = resample_candles(m5, "H1")  if m5 else []
        h4  = resample_candles(m5, "H4")  if m5 else []
        d1  = resample_candles(m5, "D1")  if m5 else []

        # Indicator cache (based on H1 for higher-TF context)
        async with self._locks[pair]:
            if "H1" not in self._indicator_cache[pair]:
                self._indicator_cache[pair]["H1"] = compute_all(h1)
            indicators = self._indicator_cache[pair]["H1"]

        return MarketSnapshot(
            pair=pair,
            current_tick=tick,
            candles_m5=m5[-_SNAPSHOT_LIMITS["M5"]:],
            candles_m15=m15[-_SNAPSHOT_LIMITS["M15"]:],
            candles_m30=m30[-_SNAPSHOT_LIMITS["M30"]:],
            candles_h1=h1[-_SNAPSHOT_LIMITS["H1"]:],
            candles_h4=h4[-_SNAPSHOT_LIMITS["H4"]:],
            candles_d1=d1[-_SNAPSHOT_LIMITS["D1"]:],
            indicators=indicators,
            session=detect_session(),
            snapshot_time=utcnow(),
        )
