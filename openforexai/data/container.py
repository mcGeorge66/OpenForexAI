from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from openforexai.data.resampler import resample_candles
from openforexai.models.market import Candle, MarketSnapshot, Tick
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.data_container import AbstractDataContainer
from openforexai.utils.logging import get_logger
from openforexai.utils.time_utils import detect_session, utcnow

_log = get_logger(__name__)

# How many M5 candles to back-fill from the broker when DB is empty (~4 weeks)
_M5_BACKFILL = 4 * 7 * 24 * 12   # 8 064

# How many candles to inspect when checking/repairing gaps
_GAP_CHECK_COUNT = 200

# Max candles returned per timeframe by get_snapshot() and default for get_candles()
_SNAPSHOT_LIMITS: dict[str, int] = {
    "M5":  300,
    "M15": 150,
    "M30": 100,
    "H1":  200,
    "H4":  100,
    "D1":   60,
}

# Number of M5 bars that make up one bar of each derived timeframe
_TF_M5_MULTIPLIER: dict[str, int] = {
    "M15":   3,
    "M30":   6,
    "H1":   12,
    "H4":   48,
    "D1":  288,
}

# All timeframes that are derived on-demand from M5
_DERIVED_TIMEFRAMES = ("M15", "M30", "H1", "H4", "D1")

# Additional DB lookback to compensate filtered-out synthetic null candles.
_NULL_FILTER_BUFFER_M5 = 7 * 24 * 12  # one week of M5 bars
_M5_STEP = timedelta(minutes=5)


class DataContainer:
    """Multi-broker, event-driven, fully-persistent data store.

    Architecture
    ------------
    * One ``DataContainer`` instance serves the whole system.
    * Each broker registers its pairs via ``register_broker()``.
    * Data is keyed by ``(broker_name, pair)`` throughout.
    * M5 candles arrive via ``EventType.M5_CANDLE_AVAILABLE`` on the EventBus.
      Each candle is written **directly** to the ``AbstractDataContainer`` (DB)
      — there is no in-memory rolling window.  A power outage cannot cause data
      loss.
    * Higher timeframes (M15, M30, H1, H4, D1) are derived on-demand by
      reading M5 data from the DB and passing it through the resampler — no
      separate broker API calls are needed.
    * Gap detection triggers a repair workflow that back-fills missing M5 bars
      from the broker and persists them to the DB.
    * A tiny per-pair ``_last_ts`` dict caches only the last known timestamp
      (not candle data) to allow cheap duplicate detection on incoming M5 bars.

    Table naming in the store (handled by the adapter)::

        {broker_name}_{pair}_{timeframe}  →  OAPR1_EURUSD_M5

    Usage
    -----
    ::

        container = DataContainer(store=data_container, event_bus=bus, monitoring_bus=mon)
        container.register_broker(oanda_broker, ["EURUSD", "USDJPY"])
        container.subscribe_to_bus()   # wires EventBus subscriptions
        await container.initialize()   # back-fills from broker if DB is empty
    """

    def __init__(
        self,
        store: AbstractDataContainer | None = None,
        event_bus=None,
        monitoring_bus=None,
        *,
        # Backward-compat: old code passed repository=... as a keyword arg
        repository: AbstractDataContainer | None = None,
    ) -> None:
        effective_store = store if store is not None else repository
        if effective_store is None:
            raise ValueError(
                "DataContainer requires a store (AbstractDataContainer). "
                "Pass it as the first positional argument or as store=... / repository=..."
            )
        self._store = effective_store
        # Backward-compat alias: code that accesses self._repository still works
        self._repository = effective_store
        self._event_bus = event_bus
        self._monitoring = monitoring_bus

        # Tracks which (broker_name, pair) tuples have been registered
        self._registered: set[tuple[str, str]] = set()

        # Per-pair asyncio locks guard concurrent DB writes
        self._write_locks: dict[tuple[str, str], asyncio.Lock] = {}

        # Lightweight dedup cache: only the last persisted timestamp per pair.
        # No candle data is cached — all reads go directly to the DB.
        self._last_ts: dict[tuple[str, str], datetime | None] = {}

        # broker short_name → AbstractBroker instance (for repair / back-fill)
        self._brokers: dict[str, AbstractBroker] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register_broker(self, broker: AbstractBroker, pairs: list[str]) -> None:
        """Register a broker and its tracked pairs.  Call before ``initialize()``."""
        self._brokers[broker.short_name] = broker
        for pair in pairs:
            key = (broker.short_name, pair)
            if key not in self._registered:
                self._registered.add(key)
                self._write_locks[key] = asyncio.Lock()
                self._last_ts[key] = None

    def subscribe_to_bus(self) -> None:
        """Wire EventBus subscriptions.  Call once after ``register_broker()``."""
        self._event_bus.subscribe(EventType.M5_CANDLE_AVAILABLE,    self._on_m5_candle)
        self._event_bus.subscribe(EventType.CANDLE_GAP_DETECTED,    self._on_gap_detected)
        self._event_bus.subscribe(EventType.CANDLE_REPAIR_REQUESTED, self._on_repair_requested)

    # ── Initialisation ────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Ensure the DB has M5 history for every registered (broker, pair).

        If the DB is empty for a pair, the last ``_M5_BACKFILL`` M5 candles are
        fetched from the broker and persisted.  If the DB already has data, no
        broker call is made.
        """
        tasks = [
            self._init_pair(broker_name, pair)
            for (broker_name, pair) in self._registered
        ]
        await asyncio.gather(*tasks)

    async def _init_pair(self, broker_name: str, pair: str) -> None:
        key = (broker_name, pair)

        # Probe DB: get the most recent candle (returns newest-first, limit 1)
        recent = await self._store.get_candles(broker_name, pair, "M5", limit=1)
        if recent:
            # DB already has data — record last known timestamp for dedup
            self._last_ts[key] = recent[0].timestamp
            _log.info(
                "DB has M5 data — skipping back-fill",
                broker=broker_name, pair=pair,
                latest=recent[0].timestamp.isoformat(),
            )
            return

        # DB empty — back-fill from broker
        broker = self._brokers.get(broker_name)
        if broker is None:
            _log.warning(
                "No broker registered for %s — cannot back-fill %s", broker_name, pair
            )
            return

        candles = await broker.get_historical_m5_candles(pair, _M5_BACKFILL)
        if candles:
            await self._store.save_candles_bulk(broker_name, pair, candles)
            # Broker returns oldest-first; last element is the most recent
            self._last_ts[key] = candles[-1].timestamp
        _log.info(
            "Back-filled M5 from broker",
            broker=broker_name, pair=pair, count=len(candles),
        )

    # ── EventBus handlers ─────────────────────────────────────────────────────

    async def _on_m5_candle(self, message: AgentMessage) -> None:
        """Persist a new M5 candle arriving from a broker adapter."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        candle_data = payload.get("candle", {})

        key = (broker_name, pair)
        if key not in self._registered:
            _log.debug("Ignoring candle for unregistered key %s/%s", broker_name, pair)
            return

        candle = Candle(**candle_data)

        lock = self._write_locks.get(key)
        if lock is None:
            return

        async with lock:
            # Cheap dedup using the cached last timestamp — no extra DB call
            last_ts = self._last_ts.get(key)
            if last_ts is not None and candle.timestamp <= last_ts:
                return  # already stored or stale

            await self._store.save_candle(broker_name, pair, candle)
            self._last_ts[key] = candle.timestamp

        self._emit(
            "data_container",
            MonitoringEventType.TIMEFRAME_CALCULATED,
            broker_name=broker_name,
            pair=pair,
            timeframe="M5",
            timestamp=candle.timestamp.isoformat(),
        )

    async def _on_gap_detected(self, message: AgentMessage) -> None:
        """Forward a gap-detected notification as a repair request on the bus."""
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
        """Back-fill missing M5 candles and persist them to the DB."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        await self._repair(broker_name, pair)

    # ── Gap repair ────────────────────────────────────────────────────────────

    async def _repair(self, broker_name: str, pair: str) -> None:
        """Fetch the last ``_GAP_CHECK_COUNT`` M5 candles, fill any gaps, persist."""
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

            key = (broker_name, pair)
            lock = self._write_locks.get(key)
            new_candles: list[Candle] = []

            async with lock:
                # Load existing timestamps from DB (newest-first, same window)
                existing = await self._store.get_candles(
                    broker_name, pair, "M5", limit=_GAP_CHECK_COUNT
                )
                existing_ts = {c.timestamp for c in existing}
                new_candles = [c for c in fresh if c.timestamp not in existing_ts]

                if new_candles:
                    await self._store.save_candles_bulk(broker_name, pair, new_candles)
                    # Update dedup cache with the newest repaired candle
                    max_ts = max(c.timestamp for c in new_candles)
                    current_last = self._last_ts.get(key)
                    if current_last is None or max_ts > current_last:
                        self._last_ts[key] = max_ts

            self._emit(
                "data_container", MonitoringEventType.CANDLE_REPAIR_COMPLETED,
                broker_name=broker_name, pair=pair, filled=len(new_candles),
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

    @staticmethod
    def _is_null_candle(candle: Candle) -> bool:
        return (
            candle.open == 0
            and candle.high == 0
            and candle.low == 0
            and candle.close == 0
            and candle.spread == 0
            and candle.tick_volume == 0
        )

    @classmethod
    def _drop_null_candles(cls, candles: list[Candle]) -> list[Candle]:
        return [c for c in candles if not cls._is_null_candle(c)]

    @staticmethod
    def _count_m5_gaps(candles_oldest_first: list[Candle]) -> int:
        """Return number of missing M5 bars based on timestamp discontinuities."""
        if len(candles_oldest_first) < 2:
            return 0
        missing = 0
        expected_step = _M5_STEP
        for prev, curr in zip(candles_oldest_first, candles_oldest_first[1:]):
            if curr.timestamp <= prev.timestamp:
                continue
            delta = curr.timestamp - prev.timestamp
            if delta > expected_step:
                # Example: 10 minutes gap => 1 missing candle
                missing += max(0, int(delta.total_seconds() // 300) - 1)
        return missing

    @staticmethod
    def _latest_completed_m5_open(now: datetime | None = None) -> datetime:
        dt = now or datetime.now(timezone.utc)
        slot_minute = dt.minute - (dt.minute % 5)
        boundary = dt.replace(minute=slot_minute, second=0, microsecond=0)
        return boundary - _M5_STEP

    @staticmethod
    def _build_null_m5_candle(ts: datetime) -> Candle:
        return Candle(
            timestamp=ts,
            open=Decimal("0"),
            high=Decimal("0"),
            low=Decimal("0"),
            close=Decimal("0"),
            tick_volume=0,
            spread=Decimal("0"),
            timeframe="M5",
        )

    def _missing_slots_in_recent_window(
        self,
        existing_newest_first: list[Candle],
        required_m5_count: int,
    ) -> list[datetime]:
        if required_m5_count <= 0:
            return []

        if existing_newest_first:
            end_ts = max(c.timestamp for c in existing_newest_first)
        else:
            end_ts = self._latest_completed_m5_open()
        start_ts = end_ts - _M5_STEP * (required_m5_count - 1)

        existing_set = {c.timestamp for c in existing_newest_first}
        missing: list[datetime] = []
        ts = start_ts
        while ts <= end_ts:
            if ts not in existing_set:
                missing.append(ts)
            ts += _M5_STEP
        return missing

    async def _ensure_m5_complete_for_read(
        self,
        broker_name: str,
        pair: str,
        required_m5_count: int,
    ) -> None:
        """Ensure recent M5 window is complete enough for a read request.

        If candles are missing (too few rows or timestamp gaps), fetch from broker,
        persist to DB, then return. Reads remain DB-first; broker access happens
        only when incompleteness is detected.
        """
        if required_m5_count <= 0:
            return

        key = (broker_name, pair)
        if key not in self._registered:
            return

        lock = self._write_locks.get(key)
        if lock is None:
            return

        async with lock:
            existing = await self._store.get_candles(
                broker_name, pair, "M5", limit=required_m5_count
            )  # newest-first
            missing_before = self._missing_slots_in_recent_window(existing, required_m5_count)
            if not missing_before:
                return

            broker = self._brokers.get(broker_name)
            if broker is None:
                _log.warning(
                    "Cannot back-fill for read %s/%s: broker not registered",
                    broker_name, pair,
                )
                return

            # Add a small buffer to reduce repeated top-up calls for near-edge reads.
            fetch_count = max(required_m5_count + 24, _GAP_CHECK_COUNT)
            fresh = await broker.get_historical_m5_candles(pair, fetch_count)
            if fresh:
                await self._store.save_candles_bulk(broker_name, pair, fresh)
                newest = fresh[-1].timestamp
                current_last = self._last_ts.get(key)
                if current_last is None or newest > current_last:
                    self._last_ts[key] = newest

            # Re-check and fill residual gaps with synthetic null candles.
            refreshed = await self._store.get_candles(
                broker_name, pair, "M5", limit=required_m5_count
            )
            missing_after_fetch = self._missing_slots_in_recent_window(refreshed, required_m5_count)
            if missing_after_fetch:
                nulls = [self._build_null_m5_candle(ts) for ts in missing_after_fetch]
                await self._store.save_candles_bulk(broker_name, pair, nulls)
                newest_null = missing_after_fetch[-1]
                current_last = self._last_ts.get(key)
                if current_last is None or newest_null > current_last:
                    self._last_ts[key] = newest_null

            _log.info(
                "Back-filled missing M5 for read",
                broker=broker_name,
                pair=pair,
                requested=required_m5_count,
                missing=len(missing_before),
                fetched=len(fresh),
                synthesized_nulls=len(missing_after_fetch),
            )

    async def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int | None = None,
    ) -> list[Candle]:
        """Return candles for *broker_name/pair* at *timeframe*, **oldest first**.

        All data is read directly from the DB (no in-memory cache).
        M5 candles are returned as-is (after reversing the DB's newest-first
        order).  Derived timeframes (M15 … D1) are computed on-demand from M5
        by the resampler.

        Parameters
        ----------
        limit:
            Maximum number of *timeframe* candles to return.  Defaults to
            ``_SNAPSHOT_LIMITS[timeframe]`` (300 for M5, 150 for M15, etc.).
        """
        timeframe = timeframe.upper()
        effective_limit = limit if limit is not None else _SNAPSHOT_LIMITS.get(timeframe, 300)

        if timeframe == "M5":
            await self._ensure_m5_complete_for_read(
                broker_name=broker_name,
                pair=pair,
                required_m5_count=effective_limit,
            )
            # DB returns newest-first — reverse for oldest-first convention
            raw = await self._store.get_candles(
                broker_name, pair, "M5", limit=effective_limit + _NULL_FILTER_BUFFER_M5
            )
            result = self._drop_null_candles(list(reversed(raw)))[-effective_limit:]

        elif timeframe in _DERIVED_TIMEFRAMES:
            # Fetch enough M5 bars to produce the requested number of TF bars.
            # Add one extra multiplier as a safety buffer for boundary alignment.
            multiplier = _TF_M5_MULTIPLIER[timeframe]
            m5_required = effective_limit * multiplier + multiplier
            m5_limit = m5_required + _NULL_FILTER_BUFFER_M5
            await self._ensure_m5_complete_for_read(
                broker_name=broker_name,
                pair=pair,
                required_m5_count=m5_required,
            )
            raw_m5 = await self._store.get_candles(
                broker_name, pair, "M5", limit=m5_limit
            )
            m5 = self._drop_null_candles(list(reversed(raw_m5)))   # oldest first for resampler
            result = resample_candles(m5, timeframe)[-effective_limit:]

        else:
            _log.warning("Unknown timeframe %r requested for %s/%s", timeframe, broker_name, pair)
            result = []

        first_ts = result[0].timestamp.isoformat() if result else None
        last_ts  = result[-1].timestamp.isoformat() if result else None
        self._emit(
            "data_container",
            MonitoringEventType.DATA_CONTAINER_ACCESS,
            broker_name=broker_name,
            pair=pair,
            method="get_candles",
            timeframe=timeframe,
            candle_count=len(result),
            first_ts=first_ts,
            last_ts=last_ts,
        )
        return result

    async def get_snapshot(self, broker_name: str, pair: str) -> MarketSnapshot:
        """Assemble a complete ``MarketSnapshot`` for *broker_name/pair*.

        All data is read directly from the DB — no in-memory cache is used.
        The ``current_tick`` is derived from the last M5 candle close price and
        spread — no separate live-tick API call is needed.
        """
        key = (broker_name, pair)
        if key not in self._registered:
            raise ValueError(
                f"Pair {pair!r} is not tracked for broker {broker_name!r}. "
                "Call register_broker() first."
            )

        # Fetch enough M5 bars to derive D1 (the most expensive TF):
        #   60 D1 bars × 288 M5/D1 = 17 280 M5 bars.
        max_m5_needed = (
            _SNAPSHOT_LIMITS["D1"] * _TF_M5_MULTIPLIER["D1"]
            + _TF_M5_MULTIPLIER["D1"]   # one extra for boundary alignment
        )
        raw_m5 = await self._store.get_candles(
            broker_name, pair, "M5", limit=max_m5_needed + _NULL_FILTER_BUFFER_M5
        )
        m5 = self._drop_null_candles(list(reversed(raw_m5)))   # oldest first for resampler

        if not m5:
            raise ValueError(
                f"No M5 data available for {broker_name}/{pair}. "
                "Run initialize() first."
            )

        last = m5[-1]

        # Build current_tick from the last M5 close + spread
        tick = Tick(
            pair=pair,
            bid=last.close,
            ask=last.close + last.spread,
            timestamp=last.timestamp,
        )

        # Derive all higher timeframes from the fetched M5 data
        m15 = resample_candles(m5, "M15") if m5 else []
        m30 = resample_candles(m5, "M30") if m5 else []
        h1  = resample_candles(m5, "H1")  if m5 else []
        h4  = resample_candles(m5, "H4")  if m5 else []
        d1  = resample_candles(m5, "D1")  if m5 else []

        snapshot = MarketSnapshot(
            pair=pair,
            broker_name=broker_name,
            current_tick=tick,
            candles_m5= m5[ -_SNAPSHOT_LIMITS["M5"]: ],
            candles_m15=m15[-_SNAPSHOT_LIMITS["M15"]:],
            candles_m30=m30[-_SNAPSHOT_LIMITS["M30"]:],
            candles_h1= h1[ -_SNAPSHOT_LIMITS["H1"]: ],
            candles_h4= h4[ -_SNAPSHOT_LIMITS["H4"]: ],
            candles_d1= d1[ -_SNAPSHOT_LIMITS["D1"]: ],
            session=detect_session(),
            snapshot_time=utcnow(),
        )

        self._emit(
            "data_container",
            MonitoringEventType.DATA_CONTAINER_ACCESS,
            broker_name=broker_name,
            pair=pair,
            method="get_snapshot",
            bid=str(tick.bid),
            ask=str(tick.ask),
            m5_count=len(snapshot.candles_m5),
            m15_count=len(snapshot.candles_m15),
            m30_count=len(snapshot.candles_m30),
            h1_count=len(snapshot.candles_h1),
            h4_count=len(snapshot.candles_h4),
            d1_count=len(snapshot.candles_d1),
            session=str(snapshot.session),
        )
        return snapshot

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

