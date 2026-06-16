from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from openforexai.data.resampler import resample_candles
from openforexai.models.market import Candle, MarketSnapshot, Tick
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.ports.data_container import AbstractDataContainer
from openforexai.utils.logging import get_logger
from openforexai.utils.time_utils import detect_session, utcnow

_log = get_logger(__name__)

DATA_CONTAINER_ID = "SYSTM-ALL___-GA-DATA"

# How many M5 candles to back-fill from the broker when DB is empty (~4 weeks)
_M5_BACKFILL = 4 * 7 * 24 * 12   # 8 064

# How many candles to inspect when checking/repairing gaps
_GAP_CHECK_COUNT = 200

# Max candles returned per timeframe
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

_DERIVED_TIMEFRAMES = ("M15", "M30", "H1", "H4", "D1")
_NULL_FILTER_BUFFER_M5 = 7 * 24 * 12
_M5_STEP = timedelta(minutes=5)

# Timeout for broker candle fetch via bus
_BROKER_FETCH_TIMEOUT = 60.0


def _broker_adapter_id(broker_name: str, pair: str) -> str:
    """Build the bus member ID of the broker adapter for a given broker/pair."""
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


class DataContainer:
    """Multi-broker, event-driven, fully-persistent data store.

    Registered as ``SYSTM-ALL___-GA-DATA`` on the EventBus.
    All communication goes through the bus — no direct broker references.

    Handles from inbox:
    - M5_CANDLE_UPDATE        — persist incoming candle
    - CANDLE_GAP_DETECTED     — forward as CANDLE_REPAIR_REQUESTED to broker
    - CANDLE_REPAIR_REQUESTED — request candles from broker adapter
    - CANDLE_DATA_BULK        — store bulk candles received from broker
    - ACCOUNT_STATUS_UPDATED  — persist account status snapshot
    - CANDLES_REQUEST         — respond with CANDLES_RESPONSE
    - INDICATOR_REQUEST       — compute indicator and respond
    - SWING_LEVELS_REQUEST    — compute swing levels and respond
    """

    def __init__(
        self,
        store: AbstractDataContainer | None = None,
        event_bus=None,
        monitoring_bus=None,
        resample_bucket_offset_hours: int = 0,
    ) -> None:
        if store is None:
            raise ValueError(
                "DataContainer requires a store (AbstractDataContainer). "
                "Pass it as store=..."
            )
        self._store = store
        self._event_bus = event_bus
        self._monitoring = monitoring_bus
        self._resample_bucket_offset_hours = int(resample_bucket_offset_hours)
        self._registered: set[tuple[str, str]] = set()
        self._write_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._last_ts: dict[tuple[str, str], datetime | None] = {}

        # Register as bus member
        if event_bus is not None:
            self._inbox: asyncio.Queue[AgentMessage] = event_bus.register_member(DATA_CONTAINER_ID)
        else:
            self._inbox = asyncio.Queue()

    # ── Registration (pair tracking, no broker refs) ──────────────────────────

    def _ensure_pair_tracked(self, broker_name: str, pair: str) -> None:
        key = (broker_name, pair)
        if key not in self._registered:
            self._registered.add(key)
            self._write_locks[key] = asyncio.Lock()
            self._last_ts[key] = None

    # Kept for bootstrap compatibility — pairs are also auto-registered on first candle
    def register_broker(self, broker: Any, pairs: list[str]) -> None:
        """Register pairs for a broker. No broker instance is stored."""
        short_name = str(getattr(broker, "short_name", broker)).strip()
        for pair in pairs:
            self._ensure_pair_tracked(short_name, pair)

    def subscribe_to_bus(self) -> None:
        """No-op — DataContainer now uses run() instead of handler subscriptions."""
        pass

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """No-op — data loads lazily on demand."""
        return

    async def _initial_backfill(self) -> None:
        """Request historical M5 candles from broker for all registered pairs on startup."""
        await asyncio.sleep(5)  # wait for broker adapters to finish connecting
        for broker_name, pair in list(self._registered):
            existing = await self._store.get_candles(broker_name, pair, "M5", limit=1)
            if existing:
                _log.info("DataContainer: %s/%s already has M5 data — skipping backfill",
                          broker_name, pair)
                continue
            _log.info("DataContainer: requesting initial backfill %s/%s", broker_name, pair)
            try:
                candles = await self._fetch_candles_from_broker(broker_name, pair, _M5_BACKFILL,
                                                                  timeout=120.0)
                if candles:
                    await self._store.save_candles_bulk(broker_name, pair, candles)
                    _log.info("DataContainer: backfilled %d M5 candles for %s/%s",
                              len(candles), broker_name, pair)
            except Exception as exc:
                _log.warning("DataContainer: backfill failed %s/%s: %s", broker_name, pair, exc)

    async def run(self) -> None:
        """Process incoming bus messages until cancelled."""
        _log.info("DataContainer started", member_id=DATA_CONTAINER_ID)
        asyncio.create_task(self._initial_backfill(), name="data_container_backfill")
        while True:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._handle(msg)
            except Exception as exc:
                _log.exception("DataContainer: unhandled error processing %s: %s",
                               msg.event_type, exc)

    async def _handle(self, msg: AgentMessage) -> None:
        et = msg.event_type
        if et == EventType.M5_CANDLE_UPDATE:
            await self._on_m5_candle(msg)
        elif et == EventType.CANDLE_GAP_DETECTED:
            await self._on_gap_detected(msg)
        elif et == EventType.CANDLE_REPAIR_REQUESTED:
            await self._on_repair_requested(msg)
        elif et == EventType.CANDLE_DATA_BULK:
            await self._on_candle_data_bulk(msg)
        elif et == EventType.ACCOUNT_STATUS_UPDATED:
            await self._on_account_status_updated(msg)
        elif et == EventType.CANDLES_REQUEST:
            await self._on_candles_request(msg)
        # INDICATOR_REQUEST: computation stays in calculate_indicator tool
        # (tool fetches candles via CANDLES_REQUEST and computes locally)
        # SWING_LEVELS_REQUEST is handled by the tool itself (computation stays in tool)

    # ── Broker candle fetch via bus ───────────────────────────────────────────

    async def _fetch_candles_from_broker(
        self,
        broker_name: str,
        pair: str,
        count: int,
        timeout: float = _BROKER_FETCH_TIMEOUT,
    ) -> list[Candle]:
        """Request historical candles from the broker adapter via bus."""
        if self._event_bus is None:
            return []
        target = _broker_adapter_id(broker_name, pair)
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        try:
            msg = AgentMessage(
                event_type=EventType.CANDLE_REPAIR_REQUESTED,
                source_agent_id=DATA_CONTAINER_ID,
                target_agent_id=target,
                payload={"broker_name": broker_name, "pair": pair, "count": count},
                # No correlation_id on request
            )
            future_key = str(msg.id)
            self._event_bus.register_response_future(future_key, future)
            await self._event_bus.publish(msg)
            result = await asyncio.wait_for(future, timeout=timeout)
            raw = result.get("candles", [])
            candles = []
            for cd in raw:
                try:
                    candles.append(Candle(**cd) if isinstance(cd, dict) else cd)
                except Exception:
                    pass
            return candles
        except asyncio.TimeoutError:
            _log.warning("DataContainer: broker fetch timed out for %s/%s count=%d",
                         broker_name, pair, count)
            return []
        finally:
            self._event_bus.cancel_response_future(future_key)

    # ── Message handlers ──────────────────────────────────────────────────────

    async def _on_m5_candle(self, message: AgentMessage) -> None:
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        candle_data = payload.get("candle", {})

        self._ensure_pair_tracked(broker_name, pair)
        key = (broker_name, pair)

        try:
            candle = Candle(**candle_data)
        except Exception as exc:
            _log.warning("DataContainer: invalid candle payload: %s", exc)
            return

        lock = self._write_locks.get(key)
        if lock is None:
            return

        async with lock:
            await self._store.save_candle(broker_name, pair, candle)
            last_ts = self._last_ts.get(key)
            if last_ts is None or candle.timestamp > last_ts:
                self._last_ts[key] = candle.timestamp

        self._emit(
            "data_container",
            MonitoringEventType.M5_CANDLE_SAVED,
            broker_name=broker_name,
            pair=pair,
            timeframe="M5",
            timestamp=candle.timestamp.isoformat(),
        )

    async def _on_gap_detected(self, message: AgentMessage) -> None:
        """Forward gap notification to the appropriate broker adapter."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        if not broker_name or not pair:
            return
        # Trigger repair by fetching fresh candles from broker
        await self._repair(broker_name, pair)

    async def _on_repair_requested(self, message: AgentMessage) -> None:
        """Handle external CANDLE_REPAIR_REQUESTED (e.g., from broker gap detection)."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        await self._repair(broker_name, pair)

    async def _on_candle_data_bulk(self, message: AgentMessage) -> None:
        """Store bulk candle data received from a broker adapter."""
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        raw_candles = payload.get("candles", [])
        if not broker_name or not pair or not raw_candles:
            return

        self._ensure_pair_tracked(broker_name, pair)
        key = (broker_name, pair)
        lock = self._write_locks.get(key)
        if lock is None:
            return

        candles = []
        for cd in raw_candles:
            try:
                candles.append(Candle(**cd) if isinstance(cd, dict) else cd)
            except Exception:
                pass

        if not candles:
            return

        async with lock:
            await self._store.save_candles_bulk(broker_name, pair, candles)
            newest = max(c.timestamp for c in candles)
            current_last = self._last_ts.get(key)
            if current_last is None or newest > current_last:
                self._last_ts[key] = newest

        self._emit(
            "data_container", MonitoringEventType.CANDLE_REPAIR_COMPLETED,
            broker_name=broker_name, pair=pair, filled=len(candles),
        )

    async def _on_account_status_updated(self, message: AgentMessage) -> None:
        """Persist account status received from broker adapter."""
        payload = message.payload
        try:
            from openforexai.models.account import AccountStatus
            status = AccountStatus(**payload)
            await self._store.save_account_status(status)
        except Exception as exc:
            _log.error("DataContainer: failed to persist account status: %s", exc)

    async def _on_candles_request(self, message: AgentMessage) -> None:
        """Respond to a CANDLES_REQUEST with CANDLES_RESPONSE.

        Reads from DB only — does NOT trigger broker backfill.
        Backfill happens via the background M5_CANDLE_UPDATE flow.
        """
        payload = message.payload
        broker_name = payload.get("broker_name", "")
        pair = payload.get("pair", "")
        timeframe = payload.get("timeframe", "M5")
        limit = payload.get("limit")

        try:
            candles = await self._get_candles_from_db(broker_name, pair, timeframe, limit)
            result = [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": str(c.open),
                    "high": str(c.high),
                    "low": str(c.low),
                    "close": str(c.close),
                    "tick_volume": c.tick_volume,
                    "spread": str(c.spread),
                    "timeframe": c.timeframe,
                }
                for c in candles
            ]
            error = None
        except Exception as exc:
            result = []
            error = str(exc)

        if self._event_bus is not None and message.source_agent_id:
            await self._event_bus.publish(AgentMessage(
                event_type=EventType.CANDLES_RESPONSE,
                source_agent_id=DATA_CONTAINER_ID,
                target_agent_id=message.source_agent_id,
                payload={"candles": result, "error": error},
                correlation_id=str(message.id),
            ))

    # _on_indicator_request removed — indicator computation is done in the
    # calculate_indicator tool which fetches candles via CANDLES_REQUEST and
    # computes using indicator plugins directly.

    # SWING_LEVELS_REQUEST is not handled here — swing detection computation
    # stays in the get_swing_levels tool (tool fetches candles via CANDLES_REQUEST
    # and does scipy peak detection locally)

    # ── Gap repair ────────────────────────────────────────────────────────────

    async def _repair(self, broker_name: str, pair: str) -> None:
        if not broker_name or not pair:
            return

        self._ensure_pair_tracked(broker_name, pair)
        self._emit("data_container", MonitoringEventType.CANDLE_REPAIR_STARTED,
                   broker_name=broker_name, pair=pair)
        try:
            fresh = await self._fetch_candles_from_broker(broker_name, pair, _GAP_CHECK_COUNT)
            if not fresh:
                return

            key = (broker_name, pair)
            lock = self._write_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._write_locks[key] = lock

            async with lock:
                existing = await self._store.get_candles(broker_name, pair, "M5",
                                                          limit=_GAP_CHECK_COUNT)
                existing_ts = {c.timestamp for c in existing}
                new_candles = [c for c in fresh if c.timestamp not in existing_ts]
                if new_candles:
                    await self._store.save_candles_bulk(broker_name, pair, new_candles)
                    max_ts = max(c.timestamp for c in new_candles)
                    current_last = self._last_ts.get(key)
                    if current_last is None or max_ts > current_last:
                        self._last_ts[key] = max_ts

            self._emit("data_container", MonitoringEventType.CANDLE_REPAIR_COMPLETED,
                       broker_name=broker_name, pair=pair, filled=len(new_candles))
        except Exception as exc:
            _log.exception("Candle repair failed", broker=broker_name, pair=pair, error=str(exc))
            self._emit("data_container", MonitoringEventType.CANDLE_REPAIR_FAILED,
                       broker_name=broker_name, pair=pair, error=str(exc))

    # ── Data access API ───────────────────────────────────────────────────────

    @staticmethod
    def _is_null_candle(candle: Candle) -> bool:
        return (
            candle.open == 0 and candle.high == 0 and candle.low == 0
            and candle.close == 0 and candle.spread == 0 and candle.tick_volume == 0
        )

    @classmethod
    def _drop_null_candles(cls, candles: list[Candle]) -> list[Candle]:
        return [c for c in candles if not cls._is_null_candle(c)]

    @staticmethod
    def _count_m5_gaps(candles_oldest_first: list[Candle]) -> int:
        if len(candles_oldest_first) < 2:
            return 0
        missing = 0
        for prev, curr in zip(candles_oldest_first, candles_oldest_first[1:]):
            if curr.timestamp <= prev.timestamp:
                continue
            delta = curr.timestamp - prev.timestamp
            if delta > _M5_STEP:
                missing += max(0, int(delta.total_seconds() // 300) - 1)
        return missing

    @staticmethod
    def _latest_completed_m5_open(now: datetime | None = None) -> datetime:
        dt = now or datetime.now(UTC)
        slot_minute = dt.minute - (dt.minute % 5)
        boundary = dt.replace(minute=slot_minute, second=0, microsecond=0)
        return boundary - _M5_STEP

    @staticmethod
    def _build_null_m5_candle(ts: datetime) -> Candle:
        return Candle(
            timestamp=ts,
            open=Decimal("0"), high=Decimal("0"), low=Decimal("0"), close=Decimal("0"),
            tick_volume=0, spread=Decimal("0"), timeframe="M5",
        )

    def _missing_slots_in_recent_window(
        self,
        existing_newest_first: list[Candle],
        required_m5_count: int,
    ) -> list[datetime]:
        if required_m5_count <= 0:
            return []
        latest_completed = self._latest_completed_m5_open()
        if existing_newest_first:
            latest_existing = max(c.timestamp for c in existing_newest_first)
            end_ts = max(latest_existing, latest_completed)
        else:
            end_ts = latest_completed
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
        self, broker_name: str, pair: str, required_m5_count: int,
    ) -> None:
        if required_m5_count <= 0:
            return
        key = (broker_name, pair)
        if key not in self._registered:
            return
        lock = self._write_locks.get(key)
        if lock is None:
            return

        async with lock:
            existing = await self._store.get_candles(broker_name, pair, "M5",
                                                      limit=required_m5_count)
            missing_before = self._missing_slots_in_recent_window(existing, required_m5_count)
            if not missing_before:
                return

            self._emit("data_container", MonitoringEventType.CANDLE_REPAIR_STARTED,
                       broker_name=broker_name, pair=pair, reason="read_refresh",
                       requested=required_m5_count, missing=len(missing_before))

            fetch_count = max(required_m5_count + 24, _GAP_CHECK_COUNT)
            try:
                fresh = await self._fetch_candles_from_broker(broker_name, pair, fetch_count)
                if fresh:
                    await self._store.save_candles_bulk(broker_name, pair, fresh)
                    newest = fresh[-1].timestamp
                    current_last = self._last_ts.get(key)
                    if current_last is None or newest > current_last:
                        self._last_ts[key] = newest

                refreshed = await self._store.get_candles(broker_name, pair, "M5",
                                                           limit=required_m5_count)
                if not refreshed:
                    return
                missing_after = self._missing_slots_in_recent_window(refreshed, required_m5_count)
                if missing_after:
                    nulls = [self._build_null_m5_candle(ts) for ts in missing_after]
                    await self._store.save_candles_bulk(broker_name, pair, nulls)

                self._emit("data_container", MonitoringEventType.CANDLE_REPAIR_COMPLETED,
                           broker_name=broker_name, pair=pair, reason="read_refresh",
                           requested=required_m5_count, missing=len(missing_before),
                           fetched=len(fresh) if fresh else 0)
            except Exception as exc:
                self._emit("data_container", MonitoringEventType.CANDLE_REPAIR_FAILED,
                           broker_name=broker_name, pair=pair, reason="read_refresh",
                           error=str(exc))
                raise

    async def _get_candles_from_db(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int | None = None,
    ) -> list[Candle]:
        """Read candles from DB only — no broker fetch, no completeness check.

        Used for bus requests (CANDLES_REQUEST) where latency must be low.
        The caller gets whatever is currently in the DB.
        """
        broker_name = str(broker_name).strip()
        pair = str(pair).strip().upper()
        self._ensure_pair_tracked(broker_name, pair)
        timeframe = timeframe.upper()
        effective_limit = limit if limit is not None else _SNAPSHOT_LIMITS.get(timeframe, 300)

        if timeframe == "M5":
            raw = await self._store.get_candles(
                broker_name, pair, "M5", limit=effective_limit + _NULL_FILTER_BUFFER_M5
            )
            return self._drop_null_candles(list(reversed(raw)))[-effective_limit:]

        elif timeframe in _DERIVED_TIMEFRAMES:
            multiplier = _TF_M5_MULTIPLIER[timeframe]
            m5_required = effective_limit * multiplier + multiplier
            m5_limit = m5_required + _NULL_FILTER_BUFFER_M5
            raw_m5 = await self._store.get_candles(broker_name, pair, "M5", limit=m5_limit)
            m5 = self._drop_null_candles(list(reversed(raw_m5)))
            return resample_candles(
                m5, timeframe, bucket_offset_hours=self._resample_bucket_offset_hours,
            )[-effective_limit:]

        return []

    async def get_candles(
        self,
        broker_name: str,
        pair: str,
        timeframe: str,
        limit: int | None = None,
    ) -> list[Candle]:
        broker_name = str(broker_name).strip()
        pair = str(pair).strip().upper()
        self._ensure_pair_tracked(broker_name, pair)
        timeframe = timeframe.upper()
        effective_limit = limit if limit is not None else _SNAPSHOT_LIMITS.get(timeframe, 300)

        if timeframe == "M5":
            await self._ensure_m5_complete_for_read(broker_name, pair, effective_limit)
            raw = await self._store.get_candles(
                broker_name, pair, "M5", limit=effective_limit + _NULL_FILTER_BUFFER_M5
            )
            result = self._drop_null_candles(list(reversed(raw)))[-effective_limit:]

        elif timeframe in _DERIVED_TIMEFRAMES:
            multiplier = _TF_M5_MULTIPLIER[timeframe]
            m5_required = effective_limit * multiplier + multiplier
            m5_limit = m5_required + _NULL_FILTER_BUFFER_M5
            await self._ensure_m5_complete_for_read(broker_name, pair, m5_required)
            raw_m5 = await self._store.get_candles(broker_name, pair, "M5", limit=m5_limit)
            m5 = self._drop_null_candles(list(reversed(raw_m5)))
            result = resample_candles(
                m5, timeframe, bucket_offset_hours=self._resample_bucket_offset_hours,
            )[-effective_limit:]

        else:
            _log.warning("Unknown timeframe %r requested for %s/%s", timeframe, broker_name, pair)
            result = []

        self._emit(
            "data_container", MonitoringEventType.DATA_CONTAINER_ACCESS,
            broker_name=broker_name, pair=pair,
            method="get_candles", timeframe=timeframe, candle_count=len(result),
            first_ts=result[0].timestamp.isoformat() if result else None,
            last_ts=result[-1].timestamp.isoformat() if result else None,
        )
        return result

    async def get_snapshot(self, broker_name: str, pair: str) -> MarketSnapshot:
        broker_name = str(broker_name).strip()
        pair = str(pair).strip().upper()
        self._ensure_pair_tracked(broker_name, pair)

        max_m5_needed = (
            _SNAPSHOT_LIMITS["D1"] * _TF_M5_MULTIPLIER["D1"] + _TF_M5_MULTIPLIER["D1"]
        )
        await self._ensure_m5_complete_for_read(broker_name, pair, max_m5_needed)
        raw_m5 = await self._store.get_candles(
            broker_name, pair, "M5", limit=max_m5_needed + _NULL_FILTER_BUFFER_M5
        )
        m5 = self._drop_null_candles(list(reversed(raw_m5)))

        if not m5:
            raise ValueError(
                f"No M5 data available for {broker_name}/{pair}. "
                "No broker data available yet for this pair."
            )

        last = m5[-1]
        tick = Tick(pair=pair, bid=last.close, ask=last.close + last.spread,
                    timestamp=last.timestamp)

        m15 = resample_candles(m5, "M15", bucket_offset_hours=self._resample_bucket_offset_hours)
        m30 = resample_candles(m5, "M30", bucket_offset_hours=self._resample_bucket_offset_hours)
        h1  = resample_candles(m5, "H1",  bucket_offset_hours=self._resample_bucket_offset_hours)
        h4  = resample_candles(m5, "H4",  bucket_offset_hours=self._resample_bucket_offset_hours)
        d1  = resample_candles(m5, "D1",  bucket_offset_hours=self._resample_bucket_offset_hours)

        snapshot = MarketSnapshot(
            pair=pair, broker_name=broker_name, current_tick=tick,
            candles_m5= m5[ -_SNAPSHOT_LIMITS["M5"]: ],
            candles_m15=m15[-_SNAPSHOT_LIMITS["M15"]:],
            candles_m30=m30[-_SNAPSHOT_LIMITS["M30"]:],
            candles_h1= h1[ -_SNAPSHOT_LIMITS["H1"]: ],
            candles_h4= h4[ -_SNAPSHOT_LIMITS["H4"]: ],
            candles_d1= d1[ -_SNAPSHOT_LIMITS["D1"]: ],
            session=detect_session(), snapshot_time=utcnow(),
        )

        self._emit(
            "data_container", MonitoringEventType.DATA_CONTAINER_ACCESS,
            broker_name=broker_name, pair=pair, method="get_snapshot",
            bid=str(tick.bid), ask=str(tick.ask),
            m5_count=len(snapshot.candles_m5), m15_count=len(snapshot.candles_m15),
            m30_count=len(snapshot.candles_m30), h1_count=len(snapshot.candles_h1),
            h4_count=len(snapshot.candles_h4), d1_count=len(snapshot.candles_d1),
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
                timestamp=datetime.now(UTC),
                source_module=source,
                event_type=event_type,
                broker_name=broker_name,
                pair=pair,
                payload=kwargs,
            ))
        except Exception:
            pass
