from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from openforexai.models.market import Candle
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.models.trade import CloseReason, OrderBookEntry, OrderStatus, OrderType
from openforexai.ports.broker import AbstractBroker
from openforexai.runtime import control as runtime_control

_log = logging.getLogger(__name__)


def _adapter_agent_id(broker_name: str, pair: str) -> str:
    """Build the structured source_agent_id for a broker adapter.

    One adapter = one pair.  Format: ``BROKER-PAIR-AD-ADPT``
    Example: ``OANDA-EURUSD-AD-ADPT``, ``MT5__-USDJPY-AD-ADPT``
    """
    b = broker_name.upper().ljust(5, "_")[:5]
    p = pair.upper().ljust(6, "_")[:6]
    return f"{b}-{p}-AD-ADPT"


# ── Candle normalisation ──────────────────────────────────────────────────────


def normalize_candle(raw: dict[str, Any], pair: str, timeframe: str) -> Candle:
    """Convert a broker-specific OHLCV dict to a canonical Candle.

    Expected raw keys (flexible — supports both long and short names):
        time / timestamp   → timestamp
        open / o           → open (bid)
        high / h           → high (bid)
        low  / l           → low  (bid)
        close / c          → close (bid)
        tick_volume / v    → tick_volume
        spread             → spread in pips (defaults to 0 if absent)
    """
    ts = raw.get("time") or raw.get("timestamp")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, tz=UTC)

    spread_raw = raw.get("spread", 0)
    tick_vol_raw = raw.get("tick_volume", 0) or raw.get("v", 0)

    return Candle(
        timestamp=ts,
        open=Decimal(str(raw.get("open") or raw.get("o") or "0")),
        high=Decimal(str(raw.get("high") or raw.get("h") or "0")),
        low=Decimal(str(raw.get("low") or raw.get("l") or "0")),
        close=Decimal(str(raw.get("close") or raw.get("c") or "0")),
        tick_volume=int(tick_vol_raw),
        spread=Decimal(str(spread_raw)),
        timeframe=timeframe,
    )


# ── Retry helper ──────────────────────────────────────────────────────────────


async def retry_async(coro_fn, attempts: int = 3, base_delay: float = 1.0):
    """Retry an async callable with exponential back-off."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2 ** attempt))
    raise RuntimeError(f"All {attempts} attempts failed") from last_exc


# ── BrokerBase — background loop orchestration ────────────────────────────────


class BrokerBase(AbstractBroker):
    """Concrete base class that implements the three background loops.

    Subclasses implement the abstract data/order methods from AbstractBroker.
    This class wires them into the event bus and monitoring bus.

    Background tasks (started via ``start_background_tasks()``):
      1. ``_m5_loop``          — polls for new M5 candles, publishes events
      2. ``_account_poll_loop``— periodically fetches account status
      3. ``_sync_loop``        — compares broker positions with local order book

    All three tasks are fire-and-forget asyncio Tasks.  They run until
    ``stop_background_tasks()`` is called.
    """

    def __init__(self, monitoring_bus=None) -> None:
        # Injected after construction via start_background_tasks() to avoid
        # circular imports at module level.
        self._monitoring = monitoring_bus
        self._pair_tasks: dict[str, list[asyncio.Task]] = {}
        self._pairs: set[str] = set()
        self._account_poll_task: asyncio.Task | None = None
        self._sync_task: asyncio.Task | None = None
        self._request_agent_reasoning = False
        self._running = False
        # Last successfully emitted M5 candle timestamp per pair.
        self._last_m5_time_by_pair: dict[str, datetime | None] = {}
        # Missing-slot retry counter per pair and candle timestamp.
        self._pending_m5_attempts_by_pair: dict[str, dict[datetime, int]] = {}

    # ── Background task lifecycle ─────────────────────────────────────────────

    def start_background_tasks(
        self,
        pair: str,
        event_bus,                          # EventBus — avoid import cycle
        repository,                         # AbstractRepository
        account_poll_interval: int = 60,    # seconds
        sync_interval: int = 60,            # seconds
        request_agent_reasoning: bool = False,
        monitoring_bus=None,
    ) -> None:
        """Create and schedule broker background asyncio tasks.

        Account and sync tasks are broker-wide and run once per adapter instance.
        M5 streaming runs per pair.
        """
        if monitoring_bus is not None:
            self._monitoring = monitoring_bus
        if not self._running:
            self._running = True

        self._pairs.add(pair)
        self._last_m5_time_by_pair.setdefault(pair, None)
        self._pending_m5_attempts_by_pair.setdefault(pair, {})
        self._request_agent_reasoning = self._request_agent_reasoning or request_agent_reasoning

        if self._account_poll_task is None or self._account_poll_task.done():
            self._account_poll_task = asyncio.create_task(
                self._account_poll_loop(repository, account_poll_interval),
                name=f"{self.short_name}_account_poll",
            )

        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(
                self._sync_loop(repository, event_bus, sync_interval),
                name=f"{self.short_name}_sync_loop",
            )

        existing = self._pair_tasks.get(pair)
        if existing and any(not task.done() for task in existing):
            return

        self._pair_tasks[pair] = [
            asyncio.create_task(
                self._m5_loop(pair, event_bus),
                name=f"{self.short_name}_{pair}_m5_loop",
            ),
        ]

    def stop_background_tasks(self) -> None:
        self._running = False
        if self._account_poll_task is not None:
            self._account_poll_task.cancel()
            self._account_poll_task = None
        if self._sync_task is not None:
            self._sync_task.cancel()
            self._sync_task = None
        for tasks in self._pair_tasks.values():
            for task in tasks:
                task.cancel()
        self._pair_tasks.clear()
        self._pairs.clear()
        self._pending_m5_attempts_by_pair.clear()

    # ── M5 streaming loop ─────────────────────────────────────────────────────

    async def _m5_loop(self, pair: str, event_bus) -> None:
        """Wait for the next M5 boundary, fetch the candle, publish events.

        One adapter = one pair.
        """
        source = f"broker.{self.short_name}"
        source_agent_id = _adapter_agent_id(self.short_name, pair)
        while self._running:
            try:
                await runtime_control.wait_until_resumed()
                await self._sleep_until_next_m5()
                await runtime_control.wait_until_resumed()
                try:
                    expected_open = self._expected_latest_m5_open()
                    last_m5 = self._last_m5_time_by_pair.get(pair)
                    recent_candles = await self.get_historical_m5_candles(pair, count=24)
                    recent_by_ts = {c.timestamp: c for c in recent_candles if c.timestamp <= expected_open}
                    pending_attempts = self._pending_m5_attempts_by_pair.setdefault(pair, {})

                    # Refresh the last 3 completed broker candles on every cycle so
                    # provisional OHLC values get overwritten with the final MT5 values.
                    recent_completed = sorted(ts for ts in recent_by_ts if ts <= expected_open)
                    for refresh_ts in recent_completed[-3:-1]:
                        refresh_candle = recent_by_ts.get(refresh_ts)
                        if refresh_candle is None:
                            continue
                        await self._publish_m5_candle(
                            pair=pair,
                            candle=refresh_candle,
                            event_bus=event_bus,
                            source=source,
                            source_agent_id=source_agent_id,
                            refresh_only=True,
                        )

                    if last_m5 is None and recent_by_ts:
                        newest_available = max(recent_by_ts)
                        self._last_m5_time_by_pair[pair] = newest_available
                        pending_attempts.clear()
                        continue

                    if last_m5 is None:
                        continue

                    candidate_ts = last_m5 + timedelta(minutes=5)
                    missing_slots: list[datetime] = []
                    while candidate_ts <= expected_open:
                        if candidate_ts not in recent_by_ts:
                            pending_attempts[candidate_ts] = pending_attempts.get(candidate_ts, 0) + 1
                            missing_slots.append(candidate_ts)
                        candidate_ts += timedelta(minutes=5)

                    if missing_slots:
                        _log.debug(
                            "M5 slots pending broker confirmation",
                            extra={
                                "broker": self.short_name,
                                "pair": pair,
                                "slots": [ts.isoformat() for ts in missing_slots],
                                "attempts": {ts.isoformat(): pending_attempts.get(ts, 0) for ts in missing_slots},
                            },
                        )

                    candidate_ts = last_m5 + timedelta(minutes=5)
                    while candidate_ts <= expected_open:
                        candle = recent_by_ts.get(candidate_ts)
                        if candle is None:
                            attempts = pending_attempts.get(candidate_ts, 0)
                            if attempts < 3:
                                break
                            candle = self._build_null_m5_candle(candidate_ts)
                            pending_attempts.pop(candidate_ts, None)
                        else:
                            pending_attempts.pop(candidate_ts, None)

                        await self._publish_m5_candle(
                            pair=pair,
                            candle=candle,
                            event_bus=event_bus,
                            source=source,
                            source_agent_id=source_agent_id,
                        )
                        candidate_ts += timedelta(minutes=5)

                except Exception as exc:
                    # Transient server/network errors (502/503/504, connection
                    # resets, timeouts) are logged at WARNING without a traceback
                    # — they are expected during broker maintenance windows,
                    # weekends, or system shutdown and do not need investigation.
                    _TRANSIENT_MARKERS = (
                        "502", "503", "504",
                        "bad gateway", "service unavailable", "gateway timeout",
                        "connection", "timeout",
                    )
                    err_lower = str(exc).lower()
                    is_transient = any(m in err_lower for m in _TRANSIENT_MARKERS)
                    if is_transient:
                        _log.warning(
                            "M5 fetch transient error broker=%s pair=%s: %s",
                            self.short_name, pair, exc,
                        )
                    else:
                        _log.exception(
                            "M5 fetch error broker=%s pair=%s: %s",
                            self.short_name, pair, exc,
                        )
                    self._emit(
                        source, MonitoringEventType.BROKER_ERROR,
                        broker_name=self.short_name, pair=pair, error=str(exc),
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.exception("M5 loop error broker=%s: %s", self.short_name, exc)
                await asyncio.sleep(10)

    # ── Account polling loop ──────────────────────────────────────────────────

    async def _account_poll_loop(self, repository, interval_seconds: int) -> None:
        source = f"broker.{self.short_name}"
        while self._running:
            try:
                await runtime_control.wait_until_resumed()
                status = await self.get_account_status()
                await repository.save_account_status(status)
                self._emit(
                    source, MonitoringEventType.ACCOUNT_STATUS_UPDATED,
                    broker_name=self.short_name,
                    balance=str(status.balance),
                    equity=str(status.equity),
                    margin_level=status.margin_level,
                    trade_allowed=status.trade_allowed,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.warning("Account poll error", broker=self.short_name, error=str(exc))
                self._emit(
                    source, MonitoringEventType.ACCOUNT_POLL_ERROR,
                    broker_name=self.short_name, error=str(exc),
                )
            await asyncio.sleep(interval_seconds)

    # ── Order-book sync loop ──────────────────────────────────────────────────

    async def _sync_loop(
        self,
        repository,
        event_bus,
        interval_seconds: int,
    ) -> None:
        """Detect broker-side closes (SL/TP hits) and update the order book.

        Broker positions are fetched once per cycle, then checked against each
        configured pair to avoid duplicate broker reads.
        """
        source = f"broker.{self.short_name}"
        while self._running:
            await asyncio.sleep(interval_seconds)
            await runtime_control.wait_until_resumed()
            try:
                broker_positions = await self.get_open_positions()
                broker_ids = {p.broker_position_id for p in broker_positions}

                for pair in sorted(self._pairs):
                    source_agent_id = _adapter_agent_id(self.short_name, pair)
                    self._emit(
                        source, MonitoringEventType.SYNC_CHECK_STARTED,
                        broker_name=self.short_name, pair=pair,
                    )

                    local_open = await repository.get_open_order_book_entries(
                        self.short_name, pair
                    )
                    local_by_broker_order_id = {
                        entry.broker_order_id: entry
                        for entry in local_open
                        if entry.broker_order_id
                    }
                    local_by_sync_key = {
                        entry.sync_key: entry
                        for entry in local_open
                        if entry.sync_key
                    }
                    now = datetime.now(UTC)
                    discrepancies = 0
                    matched_entry_ids: set[str] = set()

                    for broker_position in broker_positions:
                        if broker_position.pair != pair:
                            continue
                        local_entry = local_by_broker_order_id.get(broker_position.broker_position_id)
                        if local_entry is None and broker_position.sync_key:
                            local_entry = local_by_sync_key.get(broker_position.sync_key)

                        if local_entry is None:
                            imported = OrderBookEntry(
                                broker_name=self.short_name,
                                broker_order_id=broker_position.broker_position_id,
                                sync_key=broker_position.sync_key,
                                pair=broker_position.pair,
                                direction=broker_position.direction,
                                order_type=OrderType.MARKET,
                                units=broker_position.units,
                                requested_price=broker_position.open_price,
                                fill_price=broker_position.open_price,
                                stop_loss=broker_position.stop_loss,
                                take_profit=broker_position.take_profit,
                                status=OrderStatus.OPEN,
                                agent_id="broker_sync",
                                prompt_version=None,
                                entry_reasoning="Imported from broker sync.",
                                signal_confidence=0.0,
                                market_context_snapshot={"source": "broker_sync_import"},
                                requested_at=broker_position.opened_at,
                                opened_at=broker_position.opened_at,
                                last_broker_sync=now,
                                sync_confirmed=True,
                            )
                            await repository.save_order_book_entry(imported)
                            matched_entry_ids.add(str(imported.id))
                            continue

                        matched_entry_ids.add(str(local_entry.id))
                        await repository.update_order_book_entry(
                            str(local_entry.id),
                            {
                                "broker_order_id": broker_position.broker_position_id,
                                "sync_key": broker_position.sync_key or local_entry.sync_key,
                                "pair": broker_position.pair,
                                "direction": broker_position.direction,
                                "units": broker_position.units,
                                "fill_price": broker_position.open_price,
                                "stop_loss": broker_position.stop_loss,
                                "take_profit": broker_position.take_profit,
                                "status": OrderStatus.OPEN,
                                "opened_at": broker_position.opened_at,
                                "last_broker_sync": now,
                                "sync_confirmed": True,
                            },
                        )

                    for entry in local_open:
                        if str(entry.id) in matched_entry_ids:
                            continue
                        if entry.broker_order_id and entry.broker_order_id not in broker_ids:
                            discrepancies += 1
                            close_reason = CloseReason.SYNC_DETECTED

                            updates = await self._build_sync_close_updates(entry, now)
                            await repository.update_order_book_entry(
                                str(entry.id),
                                updates,
                            )

                            self._emit(
                                source, MonitoringEventType.SYNC_DISCREPANCY_FOUND,
                                broker_name=self.short_name, pair=pair,
                                entry_id=str(entry.id),
                                broker_order_id=entry.broker_order_id,
                            )

                            await event_bus.publish(AgentMessage(
                                event_type=EventType.ORDER_BOOK_SYNC_DISCREPANCY,
                                source_agent_id=source_agent_id,
                                payload={
                                    "broker_name": self.short_name,
                                    "entry_id": str(entry.id),
                                    "pair": pair,
                                    "direction": entry.direction.value,
                                    "close_reason": close_reason.value,
                                    "request_agent_reasoning": self._request_agent_reasoning,
                                },
                            ))
                            self._emit(
                                source, MonitoringEventType.SYNC_AGENT_NOTIFIED,
                                broker_name=self.short_name, pair=pair,
                                entry_id=str(entry.id),
                                request_reasoning=self._request_agent_reasoning,
                            )

                    self._emit(
                        source, MonitoringEventType.SYNC_CHECK_COMPLETED,
                        broker_name=self.short_name, pair=pair,
                        positions_at_broker=len(broker_ids),
                        local_open=len(local_open),
                        discrepancies=discrepancies,
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.exception("Sync loop error broker=%s: %s", self.short_name, exc)

    # ── Trigger a manual sync (callable by agents as a tool) ─────────────────

    async def trigger_sync(
        self,
        pair: str,
        repository,
        event_bus,
        request_agent_reasoning: bool = False,
    ) -> list[dict]:
        """Run one sync check immediately for this adapter's pair.

        Returns a list of discrepancy dicts (one per affected order book entry).
        """
        source_agent_id = _adapter_agent_id(self.short_name, pair)
        broker_positions = await self.get_open_positions()
        broker_ids = {p.broker_position_id for p in broker_positions}
        local_open = await repository.get_open_order_book_entries(self.short_name, pair)
        local_by_broker_order_id = {
            entry.broker_order_id: entry
            for entry in local_open
            if entry.broker_order_id
        }
        local_by_sync_key = {
            entry.sync_key: entry
            for entry in local_open
            if entry.sync_key
        }
        now = datetime.now(UTC)
        found: list[dict] = []
        matched_entry_ids: set[str] = set()

        for broker_position in broker_positions:
            if broker_position.pair != pair:
                continue
            local_entry = local_by_broker_order_id.get(broker_position.broker_position_id)
            if local_entry is None and broker_position.sync_key:
                local_entry = local_by_sync_key.get(broker_position.sync_key)

            if local_entry is None:
                imported = OrderBookEntry(
                    broker_name=self.short_name,
                    broker_order_id=broker_position.broker_position_id,
                    sync_key=broker_position.sync_key,
                    pair=broker_position.pair,
                    direction=broker_position.direction,
                    order_type=OrderType.MARKET,
                    units=broker_position.units,
                    requested_price=broker_position.open_price,
                    fill_price=broker_position.open_price,
                    stop_loss=broker_position.stop_loss,
                    take_profit=broker_position.take_profit,
                    status=OrderStatus.OPEN,
                    agent_id="broker_sync",
                    prompt_version=None,
                    entry_reasoning="Imported from broker sync.",
                    signal_confidence=0.0,
                    market_context_snapshot={"source": "broker_sync_import"},
                    requested_at=broker_position.opened_at,
                    opened_at=broker_position.opened_at,
                    last_broker_sync=now,
                    sync_confirmed=True,
                )
                await repository.save_order_book_entry(imported)
                matched_entry_ids.add(str(imported.id))
                continue

            matched_entry_ids.add(str(local_entry.id))
            await repository.update_order_book_entry(
                str(local_entry.id),
                {
                    "broker_order_id": broker_position.broker_position_id,
                    "sync_key": broker_position.sync_key or local_entry.sync_key,
                    "pair": broker_position.pair,
                    "direction": broker_position.direction,
                    "units": broker_position.units,
                    "fill_price": broker_position.open_price,
                    "stop_loss": broker_position.stop_loss,
                    "take_profit": broker_position.take_profit,
                    "status": OrderStatus.OPEN,
                    "opened_at": broker_position.opened_at,
                    "last_broker_sync": now,
                    "sync_confirmed": True,
                },
            )

        for entry in local_open:
            if str(entry.id) in matched_entry_ids:
                continue
            if entry.broker_order_id and entry.broker_order_id not in broker_ids:
                updates = await self._build_sync_close_updates(entry, now)
                await repository.update_order_book_entry(
                    str(entry.id),
                    updates,
                )
                disc = {
                    "entry_id": str(entry.id),
                    "pair": pair,
                    "direction": entry.direction.value,
                    "close_reason": CloseReason.SYNC_DETECTED.value,
                }
                found.append(disc)
                await event_bus.publish(AgentMessage(
                    event_type=EventType.ORDER_BOOK_SYNC_DISCREPANCY,
                    source_agent_id=source_agent_id,
                    payload={
                        "broker_name": self.short_name,
                        **disc,
                        "request_agent_reasoning": request_agent_reasoning,
                    },
                ))

        return found

    async def _publish_m5_candle(
        self,
        *,
        pair: str,
        candle: Candle,
        event_bus,
        source: str,
        source_agent_id: str,
        refresh_only: bool = False,
    ) -> None:
        self._emit(
            source, MonitoringEventType.M5_CANDLE_FETCHED,
            broker_name=self.short_name, pair=pair,
            timestamp=candle.timestamp.isoformat(),
            open=str(candle.open),
            high=str(candle.high),
            low=str(candle.low),
            close=str(candle.close),
            spread=str(candle.spread),
            tick_volume=candle.tick_volume,
            is_null_candle=self._is_null_candle(candle),
            refresh_only=refresh_only,
        )

        if not refresh_only:
            last_ts = self._last_m5_time_by_pair.get(pair)
            if last_ts is not None:
                expected = last_ts + timedelta(minutes=5)
                if candle.timestamp > expected + timedelta(seconds=30):
                    gap_candles = int((candle.timestamp - expected).total_seconds() / 300)
                    _log.warning(
                        "M5 gap detected broker=%s pair=%s missing=%d",
                        self.short_name, pair, gap_candles,
                    )
                    self._emit(
                        source, MonitoringEventType.CANDLE_GAP_DETECTED,
                        broker_name=self.short_name, pair=pair,
                        expected=expected.isoformat(),
                        got=candle.timestamp.isoformat(),
                        missing_candles=gap_candles,
                    )
                    await event_bus.publish(AgentMessage(
                        event_type=EventType.CANDLE_GAP_DETECTED,
                        source_agent_id=source_agent_id,
                        payload={
                            "broker_name": self.short_name,
                            "pair": pair,
                            "expected_timestamp": expected.isoformat(),
                            "received_timestamp": candle.timestamp.isoformat(),
                            "missing_candles": gap_candles,
                        },
                    ))

            self._last_m5_time_by_pair[pair] = candle.timestamp

        await event_bus.publish(AgentMessage(
            event_type=EventType.M5_CANDLE_AVAILABLE,
            source_agent_id=source_agent_id,
            payload={
                "broker_name": self.short_name,
                "pair": pair,
                "candle": candle.model_dump(mode="json"),
                "is_null_candle": self._is_null_candle(candle),
                "refresh_only": refresh_only,
            },
        ))
        self._emit(
            source, MonitoringEventType.M5_CANDLE_QUEUED,
            broker_name=self.short_name, pair=pair,
            timestamp=candle.timestamp.isoformat(),
            refresh_only=refresh_only,
        )

    # ── M5 time boundary helper ───────────────────────────────────────────────

    @staticmethod
    async def _sleep_until_next_m5() -> None:
        """Sleep until 10 seconds after the next M5 candle close boundary.

        M5 candles close at :00, :05, :10, ... past the hour.
        The 10-second buffer gives the broker time to finalise the bar.
        """
        now = datetime.now(UTC)
        # Minutes since epoch
        total_minutes = int(now.timestamp() / 60)
        # Next 5-minute boundary (in minutes since epoch)
        next_boundary_minutes = ((total_minutes // 5) + 1) * 5
        next_boundary = datetime.fromtimestamp(next_boundary_minutes * 60, tz=UTC)
        # Add 10-second buffer
        target = next_boundary + timedelta(seconds=10)
        wait = (target - datetime.now(UTC)).total_seconds()
        if wait > 0:
            await asyncio.sleep(wait)

    @staticmethod
    def _expected_latest_m5_open(now: datetime | None = None) -> datetime:
        """Return open timestamp for the latest completed M5 candle."""
        dt = now or datetime.now(UTC)
        slot_minute = dt.minute - (dt.minute % 5)
        boundary = dt.replace(minute=slot_minute, second=0, microsecond=0)
        return boundary - timedelta(minutes=5)

    @staticmethod
    def _build_null_m5_candle(ts: datetime) -> Candle:
        """Create a synthetic M5 candle when broker has no fresh candle."""
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

    async def _build_sync_close_updates(self, entry: OrderBookEntry, now: datetime) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "status": OrderStatus.CLOSED,
            "close_reason": CloseReason.SYNC_DETECTED,
            "closed_at": now,
            "last_broker_sync": now,
            "sync_confirmed": True,
        }
        try:
            broker_result = await self.get_closed_trade_result(
                entry.broker_order_id or "",
                pair=entry.pair,
                sync_key=entry.sync_key,
            )
        except Exception as exc:
            _log.warning(
                "Closed trade result lookup failed during sync",
                extra={
                    "broker_name": self.short_name,
                    "pair": entry.pair,
                    "broker_order_id": entry.broker_order_id,
                    "error": str(exc),
                },
            )
            broker_result = None

        if isinstance(broker_result, dict):
            pnl = broker_result.get("pnl_account_currency")
            if isinstance(pnl, Decimal):
                updates["pnl_account_currency"] = pnl
            elif isinstance(pnl, (int, float, str)) and str(pnl).strip():
                updates["pnl_account_currency"] = Decimal(str(pnl))

            close_price = broker_result.get("close_price")
            if isinstance(close_price, Decimal):
                updates["close_price"] = close_price
            elif isinstance(close_price, (int, float, str)) and str(close_price).strip():
                updates["close_price"] = Decimal(str(close_price))

            closed_at = broker_result.get("closed_at")
            if isinstance(closed_at, datetime):
                updates["closed_at"] = closed_at

            close_reason = broker_result.get("close_reason")
            if isinstance(close_reason, str) and close_reason.strip():
                updates["close_reasoning"] = close_reason.strip()

        return updates

    # ── Monitoring helper ─────────────────────────────────────────────────────

    def _emit(
        self,
        source: str,
        event_type: MonitoringEventType,
        broker_name: str | None = None,
        pair: str | None = None,
        **kwargs,
    ) -> None:
        """Emit a monitoring event if a bus is configured."""
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
            pass  # monitoring must never crash the system





