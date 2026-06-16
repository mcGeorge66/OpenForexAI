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

# Pairs required to compute a synthetic DXY index (ICE formula components).
# The broker adapter tracks these for every trading pair automatically so that
# DXY correlation data is always available in the DataContainer.
DXY_COMPONENT_PAIRS: frozenset[str] = frozenset(
    ["EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF"]
)


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
        # Last observed trigger timestamp per pair (the second-most-recent candle).
        self._last_m5_time_by_pair: dict[str, datetime | None] = {}
        # Missing-slot retry counter per pair and candle timestamp.
        self._pending_m5_attempts_by_pair: dict[str, dict[datetime, int]] = {}
        self._agent_trigger_tasks_by_pair: dict[str, asyncio.Task] = {}
        # Pairs running as data-only DXY component loops (no agent trigger).
        # When one of these pairs is later started as a trading pair it must be
        # cancelled and restarted with emit_agent_trigger=True.
        self._dxy_only_pairs: set[str] = set()

    # ── Background task lifecycle ─────────────────────────────────────────────

    # ── Bus-based repository helper ───────────────────────────────────────────

    async def _repo_request(
        self,
        event_bus,
        source_id: str,
        operation: str,
        args: dict | None = None,
        timeout: float = 60.0,
    ):
        """Send a REPO_REQUEST to the RepositoryService and return the result."""
        from openforexai.repository_service import REPO_SERVICE_ID

        future = asyncio.get_running_loop().create_future()
        try:
            msg = AgentMessage(
                event_type=EventType.REPO_REQUEST,
                source_agent_id=source_id,
                target_agent_id=REPO_SERVICE_ID,
                payload={"operation": operation, "args": args or {}},
            )
            future_key = str(msg.id)
            event_bus.register_response_future(future_key, future)
            await event_bus.publish(msg)
            result = await asyncio.wait_for(future, timeout=timeout)
            if result.get("error"):
                raise RuntimeError(f"Repo op '{operation}' failed: {result['error']}")
            return result.get("result")
        except asyncio.TimeoutError:
            _log.warning("Broker: repo_request timed out op=%s timeout=%.0fs", operation, timeout)
            raise
        finally:
            event_bus.cancel_response_future(future_key)

    # ── Inbox processing (bus-based command handling) ─────────────────────────

    async def _inbox_loop(self, pair: str, event_bus, inbox) -> None:
        """Process incoming bus messages for this adapter+pair member."""
        source_id = _adapter_agent_id(self.short_name, pair)
        while self._running:
            try:
                msg = await asyncio.wait_for(inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            try:
                await self._handle_inbox_message(msg, source_id, event_bus)
            except Exception as exc:
                _log.exception("Broker inbox error pair=%s: %s", pair, exc)

    async def _handle_inbox_message(
        self, msg: AgentMessage, source_id: str, event_bus
    ) -> None:
        et = msg.event_type
        if et == EventType.ORDER_REQUEST:
            await self._handle_order_request(msg, source_id, event_bus)
        elif et == EventType.POSITION_CLOSE_REQUEST:
            await self._handle_close_request(msg, source_id, event_bus)
        elif et == EventType.ORDER_MODIFY_REQUEST:
            await self._handle_modify_request(msg, source_id, event_bus)
        elif et == EventType.ACCOUNT_STATUS_REQUEST:
            await self._handle_account_status_request(msg, source_id, event_bus)
        elif et == EventType.POSITIONS_REQUEST:
            await self._handle_positions_request(msg, source_id, event_bus)
        elif et == EventType.CANDLE_REPAIR_REQUESTED:
            await self._handle_candle_repair_request(msg, source_id, event_bus)

    async def _handle_order_request(self, msg: AgentMessage, source_id: str, event_bus) -> None:
        from openforexai.models.trade import TradeOrder
        payload = msg.payload
        try:
            order = TradeOrder(**payload.get("order", {}))
            result = await self.place_order(order)
            if hasattr(result, "model_dump"):
                response_payload = result.model_dump(mode="json")
            elif isinstance(result, dict):
                response_payload = result
            else:
                response_payload = {"result": str(result), "success": True}
            response_payload["error"] = None
        except Exception as exc:
            _log.error("Broker: place_order failed: %s", exc)
            response_payload = {"success": False, "error": str(exc)}

        await event_bus.publish(AgentMessage(
            event_type=EventType.ORDER_RESULT,
            source_agent_id=source_id,
            target_agent_id=msg.source_agent_id,
            payload=response_payload,
            correlation_id=str(msg.id),
        ))

    async def _handle_close_request(self, msg: AgentMessage, source_id: str, event_bus) -> None:
        payload = msg.payload
        try:
            result = await self.close_position(
                position_id=payload.get("position_id", ""),
                pair=payload.get("pair"),
                units=payload.get("units"),
            )
            result_dict = result if isinstance(result, dict) else {"result": str(result), "success": True}
            result_dict["error"] = None
        except Exception as exc:
            result_dict = {"success": False, "error": str(exc)}

        await event_bus.publish(AgentMessage(
            event_type=EventType.POSITION_CLOSE_RESULT,
            source_agent_id=source_id,
            target_agent_id=msg.source_agent_id,
            payload=result_dict,
            correlation_id=str(msg.id),
        ))

    async def _handle_modify_request(self, msg: AgentMessage, source_id: str, event_bus) -> None:
        payload = msg.payload
        try:
            result = await self.modify_position(
                position_id=payload.get("position_id", ""),
                stop_loss=payload.get("stop_loss"),
                take_profit=payload.get("take_profit"),
            )
            result_dict = result if isinstance(result, dict) else {"result": str(result), "success": True}
            result_dict["error"] = None
        except Exception as exc:
            result_dict = {"success": False, "error": str(exc)}

        await event_bus.publish(AgentMessage(
            event_type=EventType.ORDER_MODIFY_RESULT,
            source_agent_id=source_id,
            target_agent_id=msg.source_agent_id,
            payload=result_dict,
            correlation_id=str(msg.id),
        ))

    async def _handle_account_status_request(self, msg: AgentMessage, source_id: str, event_bus) -> None:
        try:
            status = await self.get_account_status()
            result = status.model_dump(mode="json")
            error = None
        except Exception as exc:
            result = {}
            error = str(exc)

        await event_bus.publish(AgentMessage(
            event_type=EventType.ACCOUNT_STATUS_RESPONSE,
            source_agent_id=source_id,
            target_agent_id=msg.source_agent_id,
            payload={"status": result, "error": error},
            correlation_id=str(msg.id),
        ))

    async def _handle_positions_request(self, msg: AgentMessage, source_id: str, event_bus) -> None:
        pair_filter = msg.payload.get("pair")
        do_sync = msg.payload.get("trigger_sync", False)
        try:
            discrepancies: list[dict] = []
            if do_sync and pair_filter:
                discrepancies = await self.trigger_sync(pair_filter, event_bus)
            positions = await self.get_open_positions()
            if pair_filter:
                positions = [p for p in positions if p.pair == pair_filter]
            result = [p.model_dump(mode="json") for p in positions]
            error = None
        except Exception as exc:
            result = []
            discrepancies = []
            error = str(exc)

        await event_bus.publish(AgentMessage(
            event_type=EventType.POSITIONS_RESPONSE,
            source_agent_id=source_id,
            target_agent_id=msg.source_agent_id,
            payload={"positions": result, "error": error, "discrepancies": discrepancies},
            correlation_id=str(msg.id),
        ))

    async def _handle_candle_repair_request(self, msg: AgentMessage, source_id: str, event_bus) -> None:
        payload = msg.payload
        pair = payload.get("pair", "")
        count = int(payload.get("count", 200))
        broker_name = payload.get("broker_name", self.short_name)
        try:
            candles = await self.get_historical_m5_candles(pair, count)
            candle_dicts = [c.model_dump(mode="json") for c in candles]
            error = None
        except Exception as exc:
            candle_dicts = []
            error = str(exc)

        await event_bus.publish(AgentMessage(
            event_type=EventType.CANDLE_DATA_BULK,
            source_agent_id=source_id,
            target_agent_id=msg.source_agent_id,
            payload={"broker_name": broker_name, "pair": pair,
                     "candles": candle_dicts, "error": error},
            correlation_id=str(msg.id),
        ))

    def start_background_tasks(
        self,
        pair: str,
        event_bus,                          # EventBus — avoid import cycle
        repository=None,                    # kept for compat — no longer used directly
        account_poll_interval: int = 60,    # seconds
        sync_interval: int = 60,            # seconds
        candle_poll_interval: int = 30,     # seconds
        # Pairs that already have a dedicated trading agent — DXY data-only
        # loops will NOT be started for these pairs (they will get their own
        # agent-trigger loop when start_background_tasks is called for them).
        trading_pairs: set[str] | None = None,
        candle_poll_lookback: int = 3,
        agent_trigger_delay_seconds: int = 60,
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

        # Register as bus member for this pair and start inbox processing
        member_id = _adapter_agent_id(self.short_name, pair)
        inbox = event_bus.register_member(member_id)
        asyncio.create_task(
            self._inbox_loop(pair, event_bus, inbox),
            name=f"{member_id}_inbox",
        )

        if self._account_poll_task is None or self._account_poll_task.done():
            self._account_poll_task = asyncio.create_task(
                self._account_poll_loop(event_bus, account_poll_interval),
                name=f"{self.short_name}_account_poll",
            )

        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(
                self._sync_loop(event_bus, sync_interval),
                name=f"{self.short_name}_sync_loop",
            )

        existing = self._pair_tasks.get(pair)
        if existing and any(not task.done() for task in existing):
            if pair in self._dxy_only_pairs:
                # Pair was running as a data-only DXY component loop.
                # Cancel it so we can restart with emit_agent_trigger=True.
                for t in existing:
                    t.cancel()
                self._dxy_only_pairs.discard(pair)
            else:
                return

        self._pair_tasks[pair] = [
            asyncio.create_task(
                self._m5_loop(
                    pair,
                    event_bus,
                    poll_interval_seconds=max(1, int(candle_poll_interval)),
                    lookback_count=max(2, int(candle_poll_lookback)),
                    agent_trigger_delay_seconds=max(0, int(agent_trigger_delay_seconds)),
                    emit_agent_trigger=True,
                ),
                name=f"{self.short_name}_{pair}_m5_loop",
            ),
        ]

        # Start data-only M5 loops for DXY component pairs.
        # Skip pairs that are already a trading pair (they get their own
        # agent-trigger loop when start_background_tasks is called for them).
        _known_trading = trading_pairs or set()
        for dxy_pair in DXY_COMPONENT_PAIRS:
            if dxy_pair == pair:
                continue
            if dxy_pair in _known_trading:
                continue
            if dxy_pair in self._pair_tasks and any(
                not t.done() for t in self._pair_tasks[dxy_pair]
            ):
                continue
            self._last_m5_time_by_pair.setdefault(dxy_pair, None)
            self._pending_m5_attempts_by_pair.setdefault(dxy_pair, {})
            self._dxy_only_pairs.add(dxy_pair)
            self._pair_tasks[dxy_pair] = [
                asyncio.create_task(
                    self._m5_loop(
                        dxy_pair,
                        event_bus,
                        poll_interval_seconds=max(1, int(candle_poll_interval)),
                        lookback_count=max(2, int(candle_poll_lookback)),
                        agent_trigger_delay_seconds=0,
                        emit_agent_trigger=False,
                    ),
                    name=f"{self.short_name}_{dxy_pair}_m5_dxy_loop",
                ),
            ]

        # Summary log — trading pair + all DXY components with their roles
        _log.info(
            "Background tasks started broker=%s trading_pair=%s (agent_trigger=True)",
            self.short_name, pair,
        )
        for dxy_pair in sorted(DXY_COMPONENT_PAIRS):
            role = "trading+dxy (shared loop)" if dxy_pair == pair else "dxy_data_only"
            _log.info(
                "DXY component tracked broker=%s pair=%s role=%s",
                self.short_name, dxy_pair, role,
            )

        self._emit(
            f"broker.{self.short_name}",
            MonitoringEventType.SYSTEM_INFO,
            broker_name=self.short_name,
            pair=pair,
            action="background_tasks_started",
            account_poll_interval=account_poll_interval,
            sync_interval=sync_interval,
            candle_poll_interval=max(1, int(candle_poll_interval)),
            candle_poll_lookback=max(2, int(candle_poll_lookback)),
            agent_trigger_delay_seconds=max(0, int(agent_trigger_delay_seconds)),
            request_agent_reasoning=self._request_agent_reasoning,
        )

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
        for task in self._agent_trigger_tasks_by_pair.values():
            task.cancel()
        self._agent_trigger_tasks_by_pair.clear()
        self._pairs.clear()
        self._pending_m5_attempts_by_pair.clear()

    # ── M5 streaming loop ─────────────────────────────────────────────────────

    async def _m5_loop(
        self,
        pair: str,
        event_bus,
        *,
        poll_interval_seconds: int = 30,
        lookback_count: int = 3,
        agent_trigger_delay_seconds: int = 60,
        emit_agent_trigger: bool = True,
    ) -> None:
        """Poll recent M5 candles and publish when a completed candle changes.

        When emit_agent_trigger is False the loop only persists candle data
        (M5_CANDLE_UPDATE) without scheduling agent trigger events.  Used for
        DXY component pairs that are tracked for indicator data only.
        """
        source = f"broker.{self.short_name}"
        source_agent_id = _adapter_agent_id(self.short_name, pair)
        first_run = True
        while self._running:
            try:
                await runtime_control.wait_until_resumed()
                if not first_run:
                    await asyncio.sleep(poll_interval_seconds)
                    await runtime_control.wait_until_resumed()
                first_run = False
                try:
                    expected_open = self._expected_latest_m5_open()
                    last_m5 = self._last_m5_time_by_pair.get(pair)
                    fetch_count = max(lookback_count, 24)
                    recent_candles = await self.get_historical_m5_candles(pair, count=fetch_count)
                    recent_window = self._select_recent_m5_window(
                        recent_candles,
                        expected_open=expected_open,
                        window_size=lookback_count,
                    )
                    if len(recent_window) < 2:
                        continue
                    trigger_candle = recent_window[-2]
                    building_candle = recent_window[-1]
                    pending_attempts = self._pending_m5_attempts_by_pair.setdefault(pair, {})
                    if last_m5 is not None:
                        expected = last_m5 + timedelta(minutes=5)
                        if trigger_candle.timestamp > expected + timedelta(seconds=30):
                            gap_candles = int((trigger_candle.timestamp - expected).total_seconds() / 300)
                            _log.warning(
                                "M5 gap detected broker=%s pair=%s missing=%d",
                                self.short_name, pair, gap_candles,
                            )
                            self._emit(
                                source, MonitoringEventType.CANDLE_GAP_DETECTED,
                                broker_name=self.short_name, pair=pair,
                                expected=expected.isoformat(),
                                got=trigger_candle.timestamp.isoformat(),
                                missing_candles=gap_candles,
                            )
                            await event_bus.publish(AgentMessage(
                                event_type=EventType.CANDLE_GAP_DETECTED,
                                source_agent_id=source_agent_id,
                                payload={
                                    "broker_name": self.short_name,
                                    "pair": pair,
                                    "expected_timestamp": expected.isoformat(),
                                    "received_timestamp": trigger_candle.timestamp.isoformat(),
                                    "missing_candles": gap_candles,
                                },
                            ))

                    if last_m5 is not None and trigger_candle.timestamp <= last_m5:
                        continue

                    self._last_m5_time_by_pair[pair] = trigger_candle.timestamp
                    pending_attempts.clear()

                    for candle in recent_window[:-1]:
                        await self._publish_m5_candle_update(
                            pair=pair,
                            candle=candle,
                            event_bus=event_bus,
                            source=source,
                            source_agent_id=source_agent_id,
                        )

                    if last_m5 is None:
                        continue

                    if emit_agent_trigger:
                        self._schedule_agent_trigger(
                            pair=pair,
                            building_candle=building_candle,
                            event_bus=event_bus,
                            source=source,
                            source_agent_id=source_agent_id,
                            expected_open=expected_open,
                            lookback_count=lookback_count,
                            delay_seconds=agent_trigger_delay_seconds,
                        )

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

    async def _account_poll_loop(self, event_bus, interval_seconds: int) -> None:
        source = f"broker.{self.short_name}"
        source_id = f"{self.short_name.upper().ljust(5,'_')[:5]}-ALL___-AD-ADPT"
        while self._running:
            try:
                await runtime_control.wait_until_resumed()
                status = await self.get_account_status()
                # Publish to bus — DataContainer (GA-DATA) receives and persists
                await event_bus.publish(AgentMessage(
                    event_type=EventType.ACCOUNT_STATUS_UPDATED,
                    source_agent_id=source_id,
                    payload=status.model_dump(mode="json"),
                ))
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
        event_bus,
        interval_seconds: int,
    ) -> None:
        """Detect broker-side closes (SL/TP hits) and update the order book via bus."""
        source = f"broker.{self.short_name}"
        source_id_base = self.short_name.upper().ljust(5, "_")[:5]
        while self._running:
            await asyncio.sleep(interval_seconds)
            await runtime_control.wait_until_resumed()
            try:
                broker_positions = await self.get_open_positions()
                broker_ids = {p.broker_position_id for p in broker_positions}

                for pair in sorted(self._pairs):
                    source_agent_id = _adapter_agent_id(self.short_name, pair)
                    self._emit(source, MonitoringEventType.SYNC_CHECK_STARTED,
                               broker_name=self.short_name, pair=pair)

                    local_open = await self._repo_request(
                        event_bus, source_agent_id,
                        "get_open_order_book_entries",
                        {"broker_name": self.short_name, "pair": pair},
                    ) or []

                    local_by_broker_order_id = {
                        entry.get("broker_order_id"): entry
                        for entry in local_open if entry.get("broker_order_id")
                    }
                    local_by_sync_key = {
                        entry.get("sync_key"): entry
                        for entry in local_open if entry.get("sync_key")
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
                                confirmed_by_broker=True,
                            )
                            await self._repo_request(
                                event_bus, source_agent_id,
                                "save_order_book_entry",
                                {"entry": imported.model_dump(mode="json")},
                            )
                            matched_entry_ids.add(str(imported.id))
                            continue

                        matched_entry_ids.add(str(local_entry.get("id", "")))
                        await self._repo_request(
                            event_bus, source_agent_id,
                            "update_order_book_entry",
                            {
                                "entry_id": local_entry.get("id"),
                                "updates": {
                                    "broker_order_id": broker_position.broker_position_id,
                                    "sync_key": broker_position.sync_key or local_entry.get("sync_key"),
                                    "fill_price": str(broker_position.open_price),
                                    "stop_loss": str(broker_position.stop_loss) if broker_position.stop_loss else None,
                                    "take_profit": str(broker_position.take_profit) if broker_position.take_profit else None,
                                    "status": OrderStatus.OPEN.value,
                                    "last_broker_sync": now.isoformat(),
                                    "sync_confirmed": True,
                                    "confirmed_by_broker": True,
                                },
                            },
                        )

                    for entry in local_open:
                        if str(entry.get("id", "")) in matched_entry_ids:
                            continue
                        if entry.get("broker_order_id") and entry["broker_order_id"] not in broker_ids:
                            discrepancies += 1
                            updates = await self._build_sync_close_updates_dict(entry, now)
                            await self._repo_request(
                                event_bus, source_agent_id,
                                "update_order_book_entry",
                                {"entry_id": entry.get("id"), "updates": updates},
                            )
                            self._emit(source, MonitoringEventType.SYNC_DISCREPANCY_FOUND,
                                       broker_name=self.short_name, pair=pair,
                                       entry_id=str(entry.get("id")),
                                       broker_order_id=entry.get("broker_order_id"))
                            await event_bus.publish(AgentMessage(
                                event_type=EventType.ORDER_BOOK_SYNC_DISCREPANCY,
                                source_agent_id=source_agent_id,
                                payload={
                                    "broker_name": self.short_name,
                                    "entry_id": str(entry.get("id")),
                                    "pair": pair,
                                    "direction": entry.get("direction"),
                                    "close_reason": CloseReason.SYNC_DETECTED.value,
                                    "request_agent_reasoning": self._request_agent_reasoning,
                                },
                            ))
                        elif not entry.get("broker_order_id"):
                            try:
                                rt = datetime.fromisoformat(
                                    str(entry["requested_at"]).replace("Z", "+00:00")
                                )
                                orphaned = (now - rt).total_seconds() > 120
                            except Exception:
                                orphaned = True
                            if orphaned:
                                discrepancies += 1
                                await self._resolve_orphaned_entry(
                                    entry, now, pair, event_bus, source_agent_id
                                )

                    self._emit(source, MonitoringEventType.SYNC_CHECK_COMPLETED,
                               broker_name=self.short_name, pair=pair,
                               positions_at_broker=len(broker_ids),
                               local_open=len(local_open),
                               discrepancies=discrepancies)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                _log.exception("Sync loop error broker=%s: %s", self.short_name, exc)

    # ── Trigger a manual sync (callable by agents as a tool) ─────────────────

    async def trigger_sync(
        self,
        pair: str,
        event_bus,
        request_agent_reasoning: bool = False,
        repository=None,  # kept for compat
    ) -> list[dict]:
        """Run one sync check immediately for this adapter's pair.

        Returns a list of discrepancy dicts (one per affected order book entry).
        """
        source_agent_id = _adapter_agent_id(self.short_name, pair)
        broker_positions = await self.get_open_positions()
        broker_ids = {p.broker_position_id for p in broker_positions}
        local_open = await self._repo_request(
            event_bus, source_agent_id,
            "get_open_order_book_entries",
            {"broker_name": self.short_name, "pair": pair},
        ) or []

        local_by_broker_order_id = {
            e.get("broker_order_id"): e for e in local_open if e.get("broker_order_id")
        }
        local_by_sync_key = {
            e.get("sync_key"): e for e in local_open if e.get("sync_key")
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
                    confirmed_by_broker=True,
                )
                await self._repo_request(
                    event_bus, source_agent_id,
                    "save_order_book_entry",
                    {"entry": imported.model_dump(mode="json")},
                )
                matched_entry_ids.add(str(imported.id))
                continue

            matched_entry_ids.add(str(local_entry.get("id", "")))
            await self._repo_request(
                event_bus, source_agent_id,
                "update_order_book_entry",
                {
                    "entry_id": local_entry.get("id"),
                    "updates": {
                        "broker_order_id": broker_position.broker_position_id,
                        "sync_key": broker_position.sync_key or local_entry.get("sync_key"),
                        "fill_price": str(broker_position.open_price),
                        "status": OrderStatus.OPEN.value,
                        "last_broker_sync": now.isoformat(),
                        "sync_confirmed": True,
                        "confirmed_by_broker": True,
                    },
                },
            )

        for entry in local_open:
            if str(entry.get("id", "")) in matched_entry_ids:
                continue
            if entry.get("broker_order_id") and entry["broker_order_id"] not in broker_ids:
                updates = await self._build_sync_close_updates_dict(entry, now)
                await self._repo_request(
                    event_bus, source_agent_id,
                    "update_order_book_entry",
                    {"entry_id": entry.get("id"), "updates": updates},
                )
                disc = {
                    "entry_id": str(entry.get("id")),
                    "pair": pair,
                    "direction": entry.get("direction"),
                    "close_reason": CloseReason.SYNC_DETECTED.value,
                }
                found.append(disc)
            elif not entry.get("broker_order_id"):
                try:
                    rt = datetime.fromisoformat(
                        str(entry["requested_at"]).replace("Z", "+00:00")
                    )
                    orphaned = (now - rt).total_seconds() > 120
                except Exception:
                    orphaned = True
                if orphaned:
                    outcome = await self._resolve_orphaned_entry(
                        entry, now, pair, event_bus, source_agent_id
                    )
                    found.append({
                        "entry_id": str(entry.get("id")),
                        "pair": pair,
                        "direction": entry.get("direction"),
                        "close_reason": CloseReason.SYNC_DETECTED.value if outcome == "closed" else CloseReason.REJECTED.value,
                    })

        return found

    def _schedule_agent_trigger(
        self,
        *,
        pair: str,
        building_candle: Candle,
        event_bus,
        source: str,
        source_agent_id: str,
        expected_open: datetime,
        lookback_count: int,
        delay_seconds: int,
    ) -> None:
        existing = self._agent_trigger_tasks_by_pair.get(pair)
        if existing is not None and not existing.done():
            existing.cancel()
        task = asyncio.create_task(
            self._delayed_candle_trigger(
                pair=pair,
                initial_building_candle=building_candle,
                event_bus=event_bus,
                source=source,
                source_agent_id=source_agent_id,
                expected_open=expected_open,
                lookback_count=lookback_count,
                delay_seconds=delay_seconds,
            ),
            name=f"{self.short_name}_{pair}_candle_trigger",
        )
        self._agent_trigger_tasks_by_pair[pair] = task

    async def _delayed_candle_trigger(
        self,
        *,
        pair: str,
        initial_building_candle: Candle,
        event_bus,
        source: str,
        source_agent_id: str,
        expected_open: datetime,
        lookback_count: int,
        delay_seconds: int,
    ) -> None:
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
                await runtime_control.wait_until_resumed()

            building_candle = initial_building_candle
            try:
                fetch_count = max(lookback_count, 24)
                refreshed = await self.get_historical_m5_candles(pair, count=fetch_count)
                refreshed_window = self._select_recent_m5_window(
                    refreshed,
                    expected_open=expected_open,
                    window_size=lookback_count,
                )
                if refreshed_window:
                    building_candle = refreshed_window[-1]
            except Exception as exc:
                _log.warning(
                    "Delayed M5 trigger refresh failed broker=%s pair=%s: %s",
                    self.short_name, pair, exc,
                )

            await self._publish_m5_candle_update(
                pair=pair,
                candle=building_candle,
                event_bus=event_bus,
                source=source,
                source_agent_id=source_agent_id,
            )
            await self._publish_m5_candle_trigger(
                pair=pair,
                candle=building_candle,
                event_bus=event_bus,
                source=source,
                source_agent_id=source_agent_id,
            )
        except asyncio.CancelledError:
            raise
        finally:
            task = self._agent_trigger_tasks_by_pair.get(pair)
            if task is asyncio.current_task():
                self._agent_trigger_tasks_by_pair.pop(pair, None)

    async def _publish_m5_candle_update(
        self,
        *,
        pair: str,
        candle: Candle,
        event_bus,
        source: str,
        source_agent_id: str,
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
        )
        await event_bus.publish(AgentMessage(
            event_type=EventType.M5_CANDLE_UPDATE,
            source_agent_id=source_agent_id,
            payload={
                "broker_name": self.short_name,
                "pair": pair,
                "candle": candle.model_dump(mode="json"),
                "is_null_candle": self._is_null_candle(candle),
            },
        ))
        self._emit(
            source, MonitoringEventType.M5_CANDLE_QUEUED,
            broker_name=self.short_name, pair=pair,
            timestamp=candle.timestamp.isoformat(),
            routed_event=EventType.M5_CANDLE_UPDATE.value,
        )

    async def _publish_m5_candle_trigger(
        self,
        *,
        pair: str,
        candle: Candle,
        event_bus,
        source: str,
        source_agent_id: str,
    ) -> None:
        _cd = candle.model_dump(mode="json")
        for _k in ("open", "high", "low", "close"):
            if _cd.get(_k) is not None:
                _cd[_k] = round(float(_cd[_k]), 5)
        if _cd.get("spread") is not None:
            _cd["spread"] = round(float(_cd["spread"]), 2)
        await event_bus.publish(AgentMessage(
            event_type=EventType.M5_CANDLE_TRIGGER,
            source_agent_id=source_agent_id,
            payload={
                "broker_name": self.short_name,
                "pair": pair,
                "candle": _cd,
                "is_null_candle": self._is_null_candle(candle),
            },
        ))
        self._emit(
            source, MonitoringEventType.M5_CANDLE_QUEUED,
            broker_name=self.short_name, pair=pair,
            timestamp=candle.timestamp.isoformat(),
            routed_event=EventType.M5_CANDLE_TRIGGER.value,
        )

    @staticmethod
    def _expected_latest_m5_open(now: datetime | None = None) -> datetime:
        """Return open timestamp for the latest completed M5 candle."""
        dt = now or datetime.now(UTC)
        slot_minute = dt.minute - (dt.minute % 5)
        boundary = dt.replace(minute=slot_minute, second=0, microsecond=0)
        return boundary - timedelta(minutes=5)

    @staticmethod
    def _select_recent_m5_window(
        candles: list[Candle],
        *,
        expected_open: datetime,
        window_size: int,
    ) -> list[Candle]:
        if not candles:
            return []
        ordered = sorted(candles, key=lambda candle: candle.timestamp)
        latest = ordered[-1]
        if latest.timestamp <= expected_open:
            completed = [c for c in ordered if c.timestamp <= expected_open]
            return completed[-window_size:]
        return ordered[-window_size:]

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

    async def _build_sync_close_updates_dict(self, entry: dict, now: datetime) -> dict[str, Any]:
        """Build update dict for a sync-detected close using dict entry (bus-based)."""
        updates: dict[str, Any] = {
            "status": OrderStatus.CLOSED.value,
            "close_reason": CloseReason.SYNC_DETECTED.value,
            "closed_at": now.isoformat(),
            "last_broker_sync": now.isoformat(),
            "sync_confirmed": True,
            "confirmed_by_broker": True,
        }
        try:
            broker_result = await self.get_closed_trade_result(
                entry.get("broker_order_id") or "",
                pair=entry.get("pair", ""),
                sync_key=entry.get("sync_key"),
            )
        except Exception as exc:
            _log.warning("Closed trade result lookup failed: %s", exc)
            broker_result = None

        if isinstance(broker_result, dict):
            for field, key in [
                ("pnl_account_currency", "pnl_account_currency"),
                ("close_price", "close_price"),
            ]:
                val = broker_result.get(key)
                if val is not None:
                    updates[field] = str(val)
            for field, key in [("closed_at", "closed_at"), ("opened_at", "opened_at")]:
                val = broker_result.get(key)
                if isinstance(val, datetime):
                    updates[field] = val.isoformat()
            close_reason = broker_result.get("close_reason")
            if isinstance(close_reason, str) and close_reason.strip():
                updates["close_reasoning"] = close_reason.strip()

        return updates

    async def _resolve_orphaned_entry(
        self,
        entry: dict,
        now: datetime,
        pair: str,
        event_bus,
        source_agent_id: str,
    ) -> str:
        """Try to recover an orphaned PENDING entry via broker history.

        Returns 'closed' if found and updated, 'rejected' otherwise.
        """
        sync_key = entry.get("sync_key")
        broker_result = None
        if sync_key:
            try:
                broker_result = await self.find_closed_trade_by_sync_key(sync_key, pair=pair)
            except Exception as exc:
                _log.warning("find_closed_trade_by_sync_key failed sync_key=%s: %s", sync_key, exc)

        if broker_result is not None:
            updates: dict = {
                "status": OrderStatus.CLOSED.value,
                "close_reason": CloseReason.SYNC_DETECTED.value,
                "closed_at": now.isoformat(),
                "last_broker_sync": now.isoformat(),
                "sync_confirmed": True,
                "confirmed_by_broker": True,
                "broker_order_id": broker_result.get("broker_order_id"),
            }
            for field, key in [
                ("pnl_account_currency", "pnl_account_currency"),
                ("fill_price", "fill_price"),
                ("close_price", "close_price"),
            ]:
                val = broker_result.get(key)
                if val is not None:
                    updates[field] = str(val)
            for field, key in [("closed_at", "closed_at"), ("opened_at", "opened_at")]:
                val = broker_result.get(key)
                if isinstance(val, datetime):
                    updates[field] = val.isoformat()
            close_reason = broker_result.get("close_reason")
            if isinstance(close_reason, str) and close_reason.strip():
                updates["close_reasoning"] = close_reason.strip()
            await self._repo_request(
                event_bus, source_agent_id,
                "update_order_book_entry",
                {"entry_id": entry.get("id"), "updates": updates},
            )
            return "closed"

        await self._repo_request(
            event_bus, source_agent_id,
            "update_order_book_entry",
            {"entry_id": entry.get("id"), "updates": {
                "status": OrderStatus.REJECTED.value,
                "last_broker_sync": now.isoformat(),
            }},
        )
        return "rejected"

    # Keep old signature for any remaining callers during migration
    async def _build_sync_close_updates(self, entry: Any, now: datetime) -> dict[str, Any]:
        if isinstance(entry, dict):
            return await self._build_sync_close_updates_dict(entry, now)
        # OrderBookEntry object
        return await self._build_sync_close_updates_dict(
            {"broker_order_id": getattr(entry, "broker_order_id", None),
             "pair": getattr(entry, "pair", ""),
             "sync_key": getattr(entry, "sync_key", None)},
            now,
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





