from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from openforexai.models.market import Candle
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.models.trade import CloseReason, OrderStatus
from openforexai.ports.broker import AbstractBroker

_log = logging.getLogger(__name__)

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
        ts = datetime.fromtimestamp(ts, tz=timezone.utc)

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
        self._tasks: list[asyncio.Task] = []
        self._running = False
        # last successfully emitted M5 candle timestamp per pair
        self._last_m5_time: dict[str, datetime] = {}

    # ── Background task lifecycle ─────────────────────────────────────────────

    def start_background_tasks(
        self,
        pairs: list[str],
        event_bus,                          # EventBus — avoid import cycle
        repository,                         # AbstractRepository
        account_poll_interval: int = 60,    # seconds
        sync_interval: int = 60,            # seconds
        request_agent_reasoning: bool = False,  # Option B if True
        monitoring_bus=None,
    ) -> None:
        """Create and schedule the three background asyncio Tasks."""
        if monitoring_bus is not None:
            self._monitoring = monitoring_bus
        self._running = True
        self._tasks = [
            asyncio.create_task(
                self._m5_loop(pairs, event_bus),
                name=f"{self.short_name}_m5_loop",
            ),
            asyncio.create_task(
                self._account_poll_loop(repository, account_poll_interval),
                name=f"{self.short_name}_account_poll",
            ),
            asyncio.create_task(
                self._sync_loop(repository, event_bus, sync_interval, request_agent_reasoning),
                name=f"{self.short_name}_sync_loop",
            ),
        ]

    def stop_background_tasks(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    # ── M5 streaming loop ─────────────────────────────────────────────────────

    async def _m5_loop(self, pairs: list[str], event_bus) -> None:
        """Wait for the next M5 boundary, fetch candles, publish events."""
        source = f"broker.{self.short_name}"
        while self._running:
            try:
                await self._sleep_until_next_m5()

                for pair in pairs:
                    try:
                        candle = await self.fetch_latest_m5_candle(pair)
                        if candle is None:
                            continue

                        self._emit(
                            source, MonitoringEventType.M5_CANDLE_FETCHED,
                            broker_name=self.short_name, pair=pair,
                            timestamp=candle.timestamp.isoformat(),
                            close=str(candle.close), spread=str(candle.spread),
                            tick_volume=candle.tick_volume,
                        )

                        # ── Gap detection ────────────────────────────────────
                        last_ts = self._last_m5_time.get(pair)
                        if last_ts is not None:
                            expected = last_ts + timedelta(minutes=5)
                            if candle.timestamp > expected + timedelta(seconds=30):
                                gap_candles = int(
                                    (candle.timestamp - expected).total_seconds() / 300
                                )
                                _log.warning(
                                    "M5 gap detected",
                                    broker=self.short_name,
                                    pair=pair,
                                    expected=expected.isoformat(),
                                    got=candle.timestamp.isoformat(),
                                    missing_candles=gap_candles,
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
                                    source_agent_id=f"broker.{self.short_name}",
                                    payload={
                                        "broker_name": self.short_name,
                                        "pair": pair,
                                        "expected_timestamp": expected.isoformat(),
                                        "received_timestamp": candle.timestamp.isoformat(),
                                        "missing_candles": gap_candles,
                                    },
                                ))

                        self._last_m5_time[pair] = candle.timestamp

                        # ── Publish candle to event bus ───────────────────────
                        await event_bus.publish(AgentMessage(
                            event_type=EventType.M5_CANDLE_AVAILABLE,
                            source_agent_id=f"broker.{self.short_name}",
                            payload={
                                "broker_name": self.short_name,
                                "pair": pair,
                                "candle": candle.model_dump(mode="json"),
                            },
                        ))
                        self._emit(
                            source, MonitoringEventType.M5_CANDLE_QUEUED,
                            broker_name=self.short_name, pair=pair,
                            timestamp=candle.timestamp.isoformat(),
                        )

                    except Exception as exc:
                        _log.exception(
                            "M5 fetch error", broker=self.short_name, pair=pair, error=str(exc)
                        )
                        self._emit(
                            source, MonitoringEventType.BROKER_ERROR,
                            broker_name=self.short_name, pair=pair, error=str(exc),
                        )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.exception("M5 loop error", broker=self.short_name, error=str(exc))
                await asyncio.sleep(10)  # brief back-off before retry

    # ── Account polling loop ──────────────────────────────────────────────────

    async def _account_poll_loop(self, repository, interval_seconds: int) -> None:
        source = f"broker.{self.short_name}"
        while self._running:
            try:
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
        request_agent_reasoning: bool,
    ) -> None:
        """Detect broker-side closes (SL/TP hits) and update the order book."""
        source = f"broker.{self.short_name}"
        while self._running:
            await asyncio.sleep(interval_seconds)
            try:
                self._emit(source, MonitoringEventType.SYNC_CHECK_STARTED,
                           broker_name=self.short_name)

                broker_positions = await self.get_open_positions()
                broker_ids = {p.broker_position_id for p in broker_positions}

                local_open = await repository.get_open_order_book_entries(self.short_name)
                now = datetime.now(timezone.utc)
                discrepancies = 0

                for entry in local_open:
                    if entry.broker_order_id and entry.broker_order_id not in broker_ids:
                        # Position gone from broker — SL/TP/trailing or broker-forced
                        discrepancies += 1
                        close_reason = CloseReason.SYNC_DETECTED

                        await repository.update_order_book_entry(
                            str(entry.id),
                            {
                                "status": OrderStatus.CLOSED,
                                "close_reason": close_reason,
                                "closed_at": now,
                                "last_broker_sync": now,
                                "sync_confirmed": True,
                            },
                        )

                        self._emit(
                            source, MonitoringEventType.SYNC_DISCREPANCY_FOUND,
                            broker_name=self.short_name, pair=entry.pair,
                            entry_id=str(entry.id),
                            broker_order_id=entry.broker_order_id,
                        )

                        await event_bus.publish(AgentMessage(
                            event_type=EventType.ORDER_BOOK_SYNC_DISCREPANCY,
                            source_agent_id=f"broker.{self.short_name}",
                            payload={
                                "broker_name": self.short_name,
                                "entry_id": str(entry.id),
                                "pair": entry.pair,
                                "direction": entry.direction.value,
                                "close_reason": close_reason.value,
                                "request_agent_reasoning": request_agent_reasoning,
                            },
                        ))
                        self._emit(
                            source, MonitoringEventType.SYNC_AGENT_NOTIFIED,
                            broker_name=self.short_name, pair=entry.pair,
                            entry_id=str(entry.id),
                            request_reasoning=request_agent_reasoning,
                        )

                self._emit(
                    source, MonitoringEventType.SYNC_CHECK_COMPLETED,
                    broker_name=self.short_name,
                    positions_at_broker=len(broker_ids),
                    local_open=len(local_open),
                    discrepancies=discrepancies,
                )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.exception("Sync loop error", broker=self.short_name, error=str(exc))

    # ── Trigger a manual sync (callable by agents as a tool) ─────────────────

    async def trigger_sync(self, repository, event_bus, request_agent_reasoning: bool = False) -> int:
        """Run one sync check immediately.  Returns the number of discrepancies found.

        Agents can call this after placing an order to confirm fill or after
        receiving a SYNC_DISCREPANCY event to re-verify the state.
        """
        broker_positions = await self.get_open_positions()
        broker_ids = {p.broker_position_id for p in broker_positions}
        local_open = await repository.get_open_order_book_entries(self.short_name)
        now = datetime.now(timezone.utc)
        discrepancies = 0

        for entry in local_open:
            if entry.broker_order_id and entry.broker_order_id not in broker_ids:
                discrepancies += 1
                await repository.update_order_book_entry(
                    str(entry.id),
                    {
                        "status": OrderStatus.CLOSED,
                        "close_reason": CloseReason.SYNC_DETECTED,
                        "closed_at": now,
                        "last_broker_sync": now,
                        "sync_confirmed": True,
                    },
                )
                await event_bus.publish(AgentMessage(
                    event_type=EventType.ORDER_BOOK_SYNC_DISCREPANCY,
                    source_agent_id=f"broker.{self.short_name}",
                    payload={
                        "broker_name": self.short_name,
                        "entry_id": str(entry.id),
                        "pair": entry.pair,
                        "direction": entry.direction.value,
                        "close_reason": CloseReason.SYNC_DETECTED.value,
                        "request_agent_reasoning": request_agent_reasoning,
                    },
                ))

        return discrepancies

    # ── M5 time boundary helper ───────────────────────────────────────────────

    @staticmethod
    async def _sleep_until_next_m5() -> None:
        """Sleep until 10 seconds after the next M5 candle close boundary.

        M5 candles close at :00, :05, :10, ... past the hour.
        The 10-second buffer gives the broker time to finalise the bar.
        """
        now = datetime.now(timezone.utc)
        # Minutes since epoch
        total_minutes = int(now.timestamp() / 60)
        # Next 5-minute boundary (in minutes since epoch)
        next_boundary_minutes = ((total_minutes // 5) + 1) * 5
        next_boundary = datetime.fromtimestamp(next_boundary_minutes * 60, tz=timezone.utc)
        # Add 10-second buffer
        target = next_boundary + timedelta(seconds=10)
        wait = (target - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            await asyncio.sleep(wait)

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
                timestamp=datetime.now(timezone.utc),
                source_module=source,
                event_type=event_type,
                broker_name=broker_name,
                pair=pair,
                payload=kwargs,
            ))
        except Exception:
            pass  # monitoring must never crash the system
