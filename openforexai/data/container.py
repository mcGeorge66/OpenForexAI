from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from openforexai.data.resampler import resample_candles
from openforexai.models.market import Candle, MarketSnapshot, Tick
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.utils.logging import get_logger
from openforexai.utils.time_utils import detect_session, utcnow

_log = get_logger(__name__)

# How many M5 candles to keep in the rolling in-memory window (~4 weeks)
_M5_ROLLING = 4 * 7 * 24 * 12   # 8 064

# How many candles to inspect when checking for gaps
_GAP_CHECK_COUNT = 200

# Snapshot window sizes per derived timeframe
_SNAPSHOT_LIMITS: dict[str, int] = {
    "M5":  300,
    "M15": 150,
    "M30": 100,
    "H1":  200,
    "H4":  100,
    "D1":   60,
}

# All timeframes derived from M5
_DERIVED_TIMEFRAMES = ("M15", "M30", "H1", "H4", "D1")


class DataContainer:
    """Multi-broker, event-driven rolling data store.

    Architecture
    ------------
    * One ``DataContainer`` instance serves the whole system.
    * Each broker registers its pairs via ``register_broker()``.
    * Data is keyed by ``(broker_name, pair)`` throughout.
    * M5 candles arrive via ``EventType.M5_CANDLE_AVAILABLE`` on the EventBus.
      The container writes them to the repository and updates the in-memory store.
    * Higher timeframes (M15, M30, H1, H4, D1) are derived on-demand from
      the M5 store via the resampler — no separate API calls needed.
    * Gap detection triggers a repair workflow that back-fills missing M5 bars
      from the broker and then recalculates affected higher timeframes.

    Table naming in the repository (handled by the repository adapter)::

        {broker_name}_{pair}_{timeframe}  →  OANDA_DEMO_EURUSD_M5

    Usage
    -----
    ::

        container = DataContainer(repository, event_bus, monitoring_bus)
        container.register_broker(oanda_broker, ["EURUSD", "USDJPY"])
        container.register_broker(mt5_broker,   ["EURUSD", "GBPUSD"])
        container.subscribe_to_bus()   # wires EventBus subscriptions
        await container.initialize()   # loads history from DB / broker
    """

    def __init__(
        self,
        repository: AbstractRepository,
        event_bus,                    # EventBus — avoid circular import
        monitoring_bus=None,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._monitoring = monitoring_bus

        # (broker_name, pair) → list[Candle M5]  (oldest first, rolling window)
        self._m5_store: dict[tuple[str, str], list[Candle]] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

        # broker short_name → AbstractBroker  (for repair requests)
        self._brokers: dict[str, AbstractBroker] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register_broker(self, broker: AbstractBroker, pairs: list[str]) -> None:
        """Register a broker and its pairs.  Must be called before initialize()."""
        self._brokers[broker.short_name] = broker
        for pair in pairs:
            key = (broker.short_name, pair)
            if key not in self._m5_store:
                self._m5_store[key] = []
                self._locks[key] = asyncio.Lock()

    def subscribe_to_bus(self) -> None:
        """Wire this container to the EventBus.  Call once after register_broker()."""
        self._event_bus.subscribe(EventType.M5_CANDLE_AVAILABLE, self._on_m5_candle)
        self._event_bus.subscribe(EventType.CANDLE_GAP_DETECTED, self._on_gap_detected)
        self._event_bus.subscribe(EventType.CANDLE_REPAIR_REQUESTED, self._on_repair_requested)

    # ── Initialisation ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Load M5 history for all registered (broker, pair) combinations.

        Load order: repository first (fast, persistent), then fill any gap
        from the broker if the repository is empty or stale.
        """
        tasks = [
            self._init_pair(broker_name, pair)
            for (broker_name, pair) in self._m5_store
        ]
        await asyncio.gather(*tasks)

    async def _init_pair(self, broker_name: str, pair: str) -> None:
        key = (broker_name, pair)
        async with self._locks[key]:
            # Try to load from repository first
            stored = await self._repository.get_candles(
                broker_name, pair, "M5", limit=_M5_ROLLING
            )
            if stored:
                # Repository returns newest-first; reverse to oldest-first
                self._m5_store[key] = list(reversed(stored))
                _log.info(
                    "Loaded M5 from repository",
                    broker=broker_name, pair=pair, count=len(stored),
                )
                return

            # Repository empty — fetch from broker
            broker = self._brokers.get(broker_name)
            if broker is None:
                _log.warning("No broker registered for %s", broker_name)
                return

            candles = await broker.get_historical_m5_candles(pair, _M5_ROLLING)
            self._m5_store[key] = candles
            if candles:
                await self._repository.save_candles_bulk(broker_name, pair, candles)
            _log.info(
                "Loaded M5 from broker",
                broker=broker_name, pair=pair, count=len(candles),
            )

    # ── EventBus handlers ─────────────────────────────────────────────────────

    async def _on_m5_candle(self, message: AgentMessage) -> None:
        """Handle a new M5 candle arriving from a broker adapter."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        candle_data = payload.get("candle", {})

        key = (broker_name, pair)
        if key not in self._m5_store:
            _log.debug("Ignoring candle for unregistered key %s/%s", broker_name, pair)
            return

        candle = Candle(**candle_data)

        async with self._locks[key]:
            store = self._m5_store[key]
            # Dedup: only append if this timestamp is newer than the last stored
            if store and candle.timestamp <= store[-1].timestamp:
                return

            store.append(candle)
            # Trim to rolling window
            if len(store) > _M5_ROLLING:
                self._m5_store[key] = store[-_M5_ROLLING:]

        # Persist asynchronously (outside the lock to avoid blocking)
        await self._repository.save_candle(broker_name, pair, candle)

        self._emit(
            "data_container",
            MonitoringEventType.TIMEFRAME_CALCULATED,
            broker_name=broker_name,
            pair=pair,
            timeframe="M5",
            timestamp=candle.timestamp.isoformat(),
        )

    async def _on_gap_detected(self, message: AgentMessage) -> None:
        """Handle a gap-detected notification from a broker adapter.

        Publishes CANDLE_REPAIR_REQUESTED on the bus so the same handler
        path (``_on_repair_requested``) runs the repair.
        """
        payload = message.payload
        await self._event_bus.publish(AgentMessage(
            event_type=EventType.CANDLE_REPAIR_REQUESTED,
            source_agent_id="data_container",
            payload={
                "broker_name": payload.get("broker_name"),
                "pair": payload.get("pair"),
            },
        ))

    async def _on_repair_requested(self, message: AgentMessage) -> None:
        """Back-fill missing M5 candles and recalculate higher timeframes."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        await self._repair(broker_name, pair)

    # ── Gap repair ────────────────────────────────────────────────────────────

    async def _repair(self, broker_name: str, pair: str) -> None:
        """Fetch the last _GAP_CHECK_COUNT M5 candles, fill any gaps, persist."""
        key = (broker_name, pair)
        broker = self._brokers.get(broker_name)
        if broker is None:
            _log.warning("Cannot repair %s/%s: broker not registered", broker_name, pair)
            return

        self._emit(
            "data_container", MonitoringEventType.CANDLE_REPAIR_STARTED,
            broker_name=broker_name, pair=pair,
        )

        try:
            fresh = await broker.get_historical_m5_candles(pair, _GAP_CHECK_COUNT)
            if not fresh:
                return

            async with self._locks[key]:
                store = self._m5_store[key]
                existing_ts = {c.timestamp for c in store}
                new_candles = [c for c in fresh if c.timestamp not in existing_ts]

                if new_candles:
                    store.extend(new_candles)
                    store.sort(key=lambda c: c.timestamp)
                    # Trim
                    if len(store) > _M5_ROLLING:
                        self._m5_store[key] = store[-_M5_ROLLING:]
                    await self._repository.save_candles_bulk(broker_name, pair, new_candles)

            self._emit(
                "data_container", MonitoringEventType.CANDLE_REPAIR_COMPLETED,
                broker_name=broker_name, pair=pair,
                filled=len(new_candles),
            )
            _log.info(
                "Candle repair complete",
                broker=broker_name, pair=pair, filled=len(new_candles),
            )

        except Exception as exc:
            _log.exception("Candle repair failed", broker=broker_name, pair=pair, error=str(exc))
            self._emit(
                "data_container", MonitoringEventType.CANDLE_REPAIR_FAILED,
                broker_name=broker_name, pair=pair, error=str(exc),
            )

    # ── Data access API ───────────────────────────────────────────────────────

    def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
    ) -> list[Candle]:
        """Return candles for *broker_name/pair* at *timeframe*.

        M5 is returned directly from the rolling store.
        All other timeframes are derived on-demand via the resampler.
        """
        key = (broker_name, pair)
        m5 = list(self._m5_store.get(key, []))
        if timeframe == "M5":
            return m5
        if timeframe in _DERIVED_TIMEFRAMES:
            return resample_candles(m5, timeframe)
        return []

    async def get_snapshot(self, broker_name: str, pair: str) -> MarketSnapshot:
        """Assemble a complete MarketSnapshot for *broker_name/pair*.

        The ``current_tick`` is derived from the last M5 candle close price
        and spread — no live tick data required.
        """
        key = (broker_name, pair)
        if key not in self._locks:
            raise ValueError(
                f"Pair {pair!r} is not tracked for broker {broker_name!r}. "
                "Call register_broker() first."
            )

        async with self._locks[key]:
            m5 = list(self._m5_store.get(key, []))

        if not m5:
            raise ValueError(
                f"No M5 data available for {broker_name}/{pair}. "
                "Run initialize() first."
            )

        last = m5[-1]

        # Derive current_tick from last M5 close bid + spread
        # spread is stored as raw price difference (ask - bid)
        tick = Tick(
            pair=pair,
            bid=last.close,
            ask=last.close + last.spread,
            timestamp=last.timestamp,
        )

        # Derive higher timeframes (outside the lock — pure computation)
        m15 = resample_candles(m5, "M15") if m5 else []
        m30 = resample_candles(m5, "M30") if m5 else []
        h1  = resample_candles(m5, "H1")  if m5 else []
        h4  = resample_candles(m5, "H4")  if m5 else []
        d1  = resample_candles(m5, "D1")  if m5 else []

        return MarketSnapshot(
            pair=pair,
            broker_name=broker_name,
            current_tick=tick,
            candles_m5=m5[-_SNAPSHOT_LIMITS["M5"]:],
            candles_m15=m15[-_SNAPSHOT_LIMITS["M15"]:],
            candles_m30=m30[-_SNAPSHOT_LIMITS["M30"]:],
            candles_h1=h1[-_SNAPSHOT_LIMITS["H1"]:],
            candles_h4=h4[-_SNAPSHOT_LIMITS["H4"]:],
            candles_d1=d1[-_SNAPSHOT_LIMITS["D1"]:],
            session=detect_session(),
            snapshot_time=utcnow(),
        )

    # ── Monitoring helper ─────────────────────────────────────────────────────

    def _emit(
        self,
        source: str,
        event_type: MonitoringEventType,
        broker_name: str | None = None,
        pair: str | None = None,
        **kwargs,
    ) -> None:
        if self._monitoring is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent

            self._monitoring.emit(MonitoringEvent(
                timestamp=datetime.now(timezone.utc),
                source_module=source,
                event_type=event_type,
                broker_name=broker_name,
                pair=pair,
                payload=kwargs,
            ))
        except Exception:
            pass
