"""Agent — the single, fully parameterised agent class for OpenForexAI.

All agent types (AA, BA, GA) use this class.  The difference between types is
exclusively determined by config and system prompt — not by code.

Bootstrap sequence
------------------
1. Agent is created with only ``(agent_id, bus, repository)``.
2. ``start()`` sends an ``AGENT_CONFIG_REQUESTED`` event to the EventBus.
3. ConfigService replies with ``AGENT_CONFIG_RESPONSE`` (direct, to this agent).
4. Agent initialises LLM, broker, tools and prompt from the received config.
5. Agent enters its run loop (timer and/or event-triggered).

Config keys (from system.json5 ``agents.<agent_id>``)
-----------------------------------------------------
llm              str                 LLM module name (RuntimeRegistry key)
broker           str | None          Broker module name — omit for GA agents
pair             str | None          Currency pair — AA agents only
timer            {enabled, interval} Periodic self-activation
event_triggers   list[str]           EventType values that wake the agent
AnyCandle       int >= 1            Divider for m5_candle_trigger triggers
session_filter   list[dict]          Optional list of {session, pre, post} — trigger
                                     fires only when at least one session is active.
                                     session: sydney|tokyo|london|new_york
                                     pre/post: minute offsets added to open/close time.
system_prompt    str                 LLM system prompt
tool_config      dict                Passed directly to ToolDispatcher

Run loop
--------
The agent's inbox receives both config responses and regular events.
Regular events that match ``event_triggers`` invoke ``_run_cycle()``.
Timer (if enabled) also invokes ``_run_cycle()`` periodically.
``_run_cycle()`` calls the LLM tool-use loop with the triggering event as
user message context.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from openforexai.agents.analysis_snapshot import (
    build_analysis_snapshot,
    build_decision_only_system_prompt,
    build_snapshot_system_prompt,
    build_snapshot_user_message,
)
from openforexai.messaging.agent_id import AgentId
from openforexai.messaging.bus import EventBus
from openforexai.messaging.llm_helpers import llm_complete, llm_complete_with_tools
from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.ports.database import AbstractRepository
from openforexai.registry.runtime_registry import RuntimeRegistry
from openforexai.runtime import control as runtime_control
from openforexai.tools import DEFAULT_REGISTRY
from openforexai.tools.base import ToolContext
from openforexai.tools.dispatcher import ToolDispatcher
from openforexai.utils.logging import get_logger

_CONFIG_TIMEOUT = 30.0   # seconds to wait for config response
_DEFAULT_MAX_TOOL_TURNS = 10
_DEFAULT_ANY_CANDLE_DIVIDER = 1
_LONG_CYCLE_WARN_SECONDS = 30.0
_QUERY_BASE_SYSTEM_PROMPT = (
    "You are a helpful trading assistant. "
    "Answer the user's question directly and concisely based on the provided market context."
)


class Agent:
    """Single parameterised agent — AA, BA, or GA.

    The type is cosmetic at runtime; only the config determines behaviour.
    """

    def __init__(
        self,
        agent_id: str,
        bus: EventBus,
        repository: AbstractRepository,
        monitoring_bus=None,
        broker_candle_utc_offset_hours: int = 3,
    ) -> None:
        self.agent_id = agent_id
        self._bus = bus
        self._repository = repository
        self._monitoring_bus = monitoring_bus
        self._broker_candle_utc_offset_hours: int = int(broker_candle_utc_offset_hours)

        self._inbox: asyncio.Queue[AgentMessage] = bus.register_agent(agent_id)
        self._running = False
        self._logger = get_logger(self.__class__.__name__).bind(agent_id=agent_id)

        # Populated after config is received
        self._config: dict[str, Any] = {}
        self._system_prompt: str = ""
        self._event_triggers: set[str] = set()
        self._llm_service_id: str | None = None   # llm:{module_name} on the bus
        self._llm_name: str | None = None          # original module name (for logging)
        self._broker = None
        self._tool_dispatcher: ToolDispatcher | None = None
        self._max_tool_turns: int = _DEFAULT_MAX_TOOL_TURNS
        self._max_tokens: int = 4096
        self._tool_context_budget_tokens: int = 32768
        self._llm_temperature: float | None = None
        self._llm_reasoning_effort: str | None = None
        self._any_candle_divider: int = _DEFAULT_ANY_CANDLE_DIVIDER
        self._m5_candle_event_count: int = 0
        self._early_trigger_enabled: bool = True
        self._pass_trigger: bool = False
        self._snapshot_profile_name: str | None = None
        self._snapshot_profile_config: dict[str, Any] = {}
        self._decision_prompt_profile_name: str | None = None
        self._decision_prompt_profile_config: dict[str, Any] = {}
        self._run_lock: asyncio.Lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Full agent lifecycle: request config → init → run."""
        self._logger.info("Agent starting — requesting config")

        # Phase 1: request config
        await self._bus.publish(AgentMessage(
            event_type=EventType.AGENT_CONFIG_REQUESTED,
            source_agent_id=self.agent_id,
            payload={"agent_id": self.agent_id},
        ))

        # Phase 2: wait for config response
        config_payload = await self._wait_for_config()
        if config_payload is None:
            self._logger.error("Config request timed out — agent will not start")
            return

        # Phase 3: initialise from config
        try:
            self._apply_config(config_payload)
        except Exception as exc:
            self._logger.exception("Agent init failed — _apply_config raised", error=str(exc))
            self._emit_system_error(f"Init failed: {type(exc).__name__}: {exc}")
            return
        self._logger.info("Config received — agent initialised")

        # Phase 4: run
        self._running = True
        timer_cfg = self._config.get("timer", {})

        try:
            async with asyncio.TaskGroup() as tg:
                if timer_cfg.get("enabled"):
                    tg.create_task(
                        self._run_timer_loop(timer_cfg.get("interval_seconds", 300)),
                        name=f"{self.agent_id}:timer",
                    )
                tg.create_task(self._run_message_loop(), name=f"{self.agent_id}:messages")
        except* Exception as eg:
            for exc in eg.exceptions:
                self._logger.exception("Agent run-loop crashed", error=str(exc))
                self._emit_system_error(f"Run-loop crash: {type(exc).__name__}: {exc}")
            # Do NOT re-raise — one crashing agent must not bring down the whole system

    async def stop(self) -> None:
        self._running = False

    # ── Config bootstrap ──────────────────────────────────────────────────────

    async def _wait_for_config(self) -> dict[str, Any] | None:
        """Drain inbox until AGENT_CONFIG_RESPONSE arrives or timeout."""
        deadline = asyncio.get_event_loop().time() + _CONFIG_TIMEOUT
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return None
            try:
                msg = await asyncio.wait_for(
                    self._inbox.get(), timeout=min(remaining, 1.0)
                )
            except TimeoutError:
                continue
            if msg.event_type == EventType.AGENT_CONFIG_RESPONSE:
                return msg.payload
        return None

    def _apply_config(self, payload: dict[str, Any]) -> None:
        """Initialise all agent internals from the received config payload."""
        cfg = payload.get("config", {})
        self._config = cfg

        self._system_prompt = cfg.get("system_prompt", "")
        self._event_triggers = set(cfg.get("event_triggers", []))
        self._any_candle_divider = self._parse_any_candle_divider(
            cfg.get("AnyCandle", _DEFAULT_ANY_CANDLE_DIVIDER)
        )
        self._m5_candle_event_count = 0
        self._early_trigger_enabled = True  # always on; no separate config key needed
        self._pass_trigger = bool(cfg.get("pass_trigger", False))
        self._session_filter: list[dict[str, Any]] = list(cfg.get("session_filter", []))
        self._snapshot_profile_name = (
            str(cfg.get("snapshot_profile")).strip() if isinstance(cfg.get("snapshot_profile"), str) and str(cfg.get("snapshot_profile")).strip() else None
        )
        self._snapshot_profile_config = (
            dict(cfg.get("snapshot_profile_config"))
            if isinstance(cfg.get("snapshot_profile_config"), dict)
            else {}
        )
        self._decision_prompt_profile_name = (
            str(cfg.get("decision_prompt_profile")).strip()
            if isinstance(cfg.get("decision_prompt_profile"), str) and str(cfg.get("decision_prompt_profile")).strip()
            else None
        )
        self._decision_prompt_profile_config = (
            dict(cfg.get("decision_prompt_profile_config"))
            if isinstance(cfg.get("decision_prompt_profile_config"), dict)
            else {}
        )
        self._fallback_snapshot_profile_config = (
            dict(cfg.get("decision_prompt_fallback_snapshot_config"))
            if isinstance(cfg.get("decision_prompt_fallback_snapshot_config"), dict)
            else {}
        )

        tool_cfg = cfg.get("tool_config", {})
        self._max_tool_turns = tool_cfg.get("max_tool_turns", _DEFAULT_MAX_TOOL_TURNS)

        # LLM — resolved via event bus (LLMService registered as llm:{module_name})
        llm_name = cfg.get("llm")
        if llm_name:
            from openforexai.services.llm_service import llm_service_id
            self._llm_name       = llm_name
            self._llm_service_id = llm_service_id(llm_name)

        # Resolve LLM runtime parameters:
        # module defaults (source of truth) -> agent overrides.
        modules = payload.get("modules", {}) if isinstance(payload.get("modules"), dict) else {}
        llm_module_cfg = modules.get("llm", {}) if isinstance(modules.get("llm"), dict) else {}

        llm_defaults: dict[str, Any] = {}
        if isinstance(llm_module_cfg.get("defaults"), dict):
            llm_defaults.update(llm_module_cfg["defaults"])
        if isinstance(llm_module_cfg.get("params"), dict):
            llm_defaults.update(llm_module_cfg["params"])
        for key in ("temperature", "max_tokens"):
            if key in llm_module_cfg:
                llm_defaults[key] = llm_module_cfg.get(key)

        llm_overrides: dict[str, Any] = {}
        if isinstance(cfg.get("llm_config"), dict):
            llm_overrides.update(cfg["llm_config"])

        resolved_llm = {**llm_defaults, **llm_overrides}

        resolved_temp = resolved_llm.get("temperature")
        self._llm_temperature = float(resolved_temp) if isinstance(resolved_temp, (int, float)) else None

        resolved_reasoning = resolved_llm.get("reasoning_effort")
        if isinstance(resolved_reasoning, str) and resolved_reasoning.strip():
            self._llm_reasoning_effort = resolved_reasoning.strip()
        else:
            self._llm_reasoning_effort = None

        resolved_llm_max = resolved_llm.get("max_tokens")
        tool_budget_max = tool_cfg.get("max_tokens")
        if isinstance(tool_budget_max, int) and tool_budget_max > 0:
            self._max_tokens = tool_budget_max
        elif isinstance(resolved_llm_max, int) and resolved_llm_max > 0:
            self._max_tokens = resolved_llm_max
        # default_max_tokens previously came from the LLM adapter directly;
        # now configure max_tokens explicitly in tool_config or llm_config.

        # Tool tier gating must use a context-sized budget, not the per-response completion limit.
        configured_context_budget = tool_cfg.get("context_budget_tokens")
        if isinstance(configured_context_budget, int) and configured_context_budget > 0:
            self._tool_context_budget_tokens = configured_context_budget
        else:
            self._tool_context_budget_tokens = max(self._max_tokens * 8, 16384)

        # Broker (optional — GA agents have no broker)
        broker_name = cfg.get("broker")
        if broker_name:
            try:
                self._broker = RuntimeRegistry.get_broker(broker_name)
            except KeyError:
                self._logger.warning("Broker %r not in RuntimeRegistry", broker_name)

        # ToolDispatcher
        # Use broker.short_name so DataContainer / DB lookups match the stored key.
        # The config module name (e.g. "oanda") differs from the runtime short_name
        # (e.g. "OAPR1") which is what register_broker() uses as the storage key.
        runtime_broker_name = (
            self._broker.short_name if self._broker is not None else broker_name
        )
        if self._llm_service_id is not None:
            context = ToolContext(
                agent_id=self.agent_id,
                broker_name=runtime_broker_name,
                pair=cfg.get("pair"),
                monitoring_bus=self._monitoring_bus,
                event_bus=self._bus,
                extra={
                    "agent_config": cfg,
                    "llm_name": llm_name,
                    "broker_module_name": broker_name,
                },
            )
            self._tool_dispatcher = ToolDispatcher(
                registry=DEFAULT_REGISTRY,
                context=context,
                agent_tool_config=tool_cfg,
            )

    def _parse_any_candle_divider(self, value: Any) -> int:
        if isinstance(value, int) and value >= 1:
            return value
        if isinstance(value, str):
            try:
                parsed = int(value)
                if parsed >= 1:
                    return parsed
            except ValueError:
                pass
        self._logger.warning(
            "Invalid AnyCandle value in agent config; fallback to 1",
            any_candle=value,
        )
        return _DEFAULT_ANY_CANDLE_DIVIDER

    def _should_run_for_trigger(self, event_val: str) -> tuple[bool, int | None]:
        if event_val != EventType.M5_CANDLE_TRIGGER.value:
            return True, None
        self._m5_candle_event_count += 1
        trigger_count = self._m5_candle_event_count
        if self._any_candle_divider <= 1:
            return True, trigger_count
        if trigger_count < self._any_candle_divider:
            self._logger.debug(
                "Skipping M5 trigger because AnyCandle divider not reached",
                any_candle=self._any_candle_divider,
                candle_count=trigger_count,
            )
            return False, trigger_count
        self._m5_candle_event_count = 0
        return True, min(trigger_count, self._any_candle_divider)

    def _maybe_accelerate_candle_counter(self, final_text: str, trigger: str) -> None:
        """If the LLM set CheckNextCandle=true, prime the counter so the next M5 candle fires immediately."""
        if not self._early_trigger_enabled:
            return
        if self._any_candle_divider <= 1:
            return
        if trigger != EventType.M5_CANDLE_TRIGGER.value:
            return
        analysis_object = self._parse_json_object(final_text)
        if not isinstance(analysis_object, dict):
            return
        if analysis_object.get("CheckNextCandle") is True:
            self._m5_candle_event_count = self._any_candle_divider
            self._logger.info(
                "Early trigger activated — next candle will re-analyse",
                agent_id=self.agent_id,
                divider=self._any_candle_divider,
            )

    # ── Session filter ────────────────────────────────────────────────────────

    def _is_session_allowed(self, candle_timestamp: datetime | None = None) -> bool:
        """Return True if the candle timestamp falls within any configured session window.

        The candle timestamp is the authoritative reference — never the system clock.
        Candle timestamps arrive in UTC+3 (broker time).  Session open/close values
        (configured in the exchange's local timezone, e.g. EDT for New York) are
        converted to UTC+3 before comparison so everything is on the same scale.

        Each entry in ``session_filter`` may specify ``pre`` and ``post`` offsets
        (minutes) relative to the session open and close times.

        Returns True immediately when no filter is configured or no candle timestamp
        is available.
        """
        if not self._session_filter:
            return True

        if candle_timestamp is None:
            # No candle timestamp available — do not block
            return True

        from datetime import timedelta, timezone
        from zoneinfo import ZoneInfo
        from openforexai.tools.market.session_status import _SESSIONS

        _SESSION_MAP = {s["name"]: s for s in _SESSIONS}

        # Normalise candle timestamp to broker time (configured UTC offset)
        broker_tz = timezone(timedelta(hours=self._broker_candle_utc_offset_hours))
        if candle_timestamp.tzinfo is None:
            ref = candle_timestamp.replace(tzinfo=broker_tz)
        else:
            ref = candle_timestamp.astimezone(broker_tz)

        for entry in self._session_filter:
            session_name = str(entry.get("session", "")).lower()
            session_def = _SESSION_MAP.get(session_name)
            if session_def is None:
                self._logger.warning("session_filter: unknown session", session=session_name)
                continue

            pre_min  = int(entry.get("pre",  0))
            post_min = int(entry.get("post", 0))

            # Convert session open/close from exchange local time to UTC+3.
            # Use the candle's date (in local exchange TZ) to handle DST correctly.
            local_tz    = ZoneInfo(session_def["tz"])
            ref_local   = ref.astimezone(local_tz)

            open_local  = ref_local.replace(
                hour=session_def["open"], minute=0, second=0, microsecond=0
            ) + timedelta(minutes=pre_min)
            close_local = ref_local.replace(
                hour=session_def["close"], minute=0, second=0, microsecond=0
            ) + timedelta(minutes=post_min)

            # Convert boundaries to UTC+3 for direct comparison with candle time
            open_broker  = open_local.astimezone(broker_tz)
            close_broker = close_local.astimezone(broker_tz)

            if open_broker <= ref <= close_broker:
                return True

        return False

    # ── Run loops ─────────────────────────────────────────────────────────────

    async def _run_timer_loop(self, interval: int) -> None:
        """Trigger run_cycle() every ``interval`` seconds.

        Fires immediately on first call so agents analyse on startup,
        then waits *interval* seconds between subsequent cycles.
        """
        first_run = True
        while self._running:
            await runtime_control.wait_until_resumed()
            if not first_run:
                await asyncio.sleep(interval)
                await runtime_control.wait_until_resumed()
            first_run = False
            if not self._is_session_allowed(None):
                self._logger.info("Timer trigger skipped — outside session filter", agent_id=self.agent_id)
                try:
                    self._monitoring_bus.emit(MonitoringEvent(
                        timestamp=datetime.now(UTC),
                        source_module=f"agent:{self.agent_id}",
                        event_type=MonitoringEventType.AGENT_TRIGGER_SKIPPED,
                        payload={
                            "agent_id": self.agent_id,
                            "trigger": "timer",
                            "reason": "session_filter",
                        },
                    ))
                except Exception:
                    pass
                continue
            try:
                await self._run_cycle(trigger="timer", payload={})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.exception("Timer cycle error", error=str(exc))
                self._emit_system_error(f"Timer cycle: {type(exc).__name__}: {exc}")

    async def _run_message_loop(self) -> None:
        """Deliver EventBus messages; invoke run_cycle for trigger events."""
        while self._running:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

            try:
                backlog_remaining = self._inbox.qsize()
                event_val = (
                    msg.event_type.value
                    if hasattr(msg.event_type, "value")
                    else str(msg.event_type)
                )
                trigger_age_ms = self._measure_trigger_age_ms(event_val, msg.payload)
                if self._is_debug_diagnostics_enabled():
                    self._emit_agent_trigger_received(
                        event_val=event_val,
                        source=msg.source_agent_id,
                        backlog_remaining=backlog_remaining,
                        trigger_age_ms=trigger_age_ms,
                    )
                    if backlog_remaining > 0:
                        self._emit_agent_backlog_detected(
                            event_val=event_val,
                            source=msg.source_agent_id,
                            backlog_remaining=backlog_remaining,
                            trigger_age_ms=trigger_age_ms,
                        )

                # agent_query is delivered directly (target_agent_id set on the
                # message), so no routing rule is needed.  Guard here is a
                # belt-and-suspenders check in case a broadcast reaches us.
                if event_val == EventType.AGENT_QUERY.value:
                    if (msg.target_agent_id is not None
                            and msg.target_agent_id != self.agent_id):
                        continue   # not addressed to us
                    await self._run_cycle(
                        trigger=event_val,
                        payload=msg.payload,
                        source=msg.source_agent_id,
                        correlation_id=str(msg.id),
                    )
                elif event_val == EventType.AGENT_CONFIG_RESPONSE.value:
                    # Runtime config refresh: re-apply config without restart.
                    try:
                        self._apply_config(msg.payload or {})
                        self._logger.info("Runtime config refresh applied")
                    except Exception as exc:
                        self._logger.exception(
                            "Runtime config refresh failed",
                            error=str(exc),
                        )
                        self._emit_system_error(
                            f"Config refresh failed: {type(exc).__name__}: {exc}"
                        )
                elif event_val in self._event_triggers:
                    should_run, trigger_count = self._should_run_for_trigger(event_val)
                    # Extract candle timestamp from trigger payload (authoritative reference)
                    candle_ts: datetime | None = None
                    candle_dict = msg.payload.get("candle") if isinstance(msg.payload, dict) else None
                    if isinstance(candle_dict, dict):
                        ts_raw = candle_dict.get("timestamp")
                        if ts_raw:
                            try:
                                candle_ts = datetime.fromisoformat(
                                    str(ts_raw).replace("Z", "+00:00")
                                )
                            except (ValueError, TypeError):
                                pass
                    session_allowed = self._is_session_allowed(candle_ts)
                    if event_val == EventType.M5_CANDLE_TRIGGER.value:
                        await self._publish_m5_trigger_counter(
                            payload=msg.payload,
                            trigger_count=trigger_count or 0,
                            divider=self._any_candle_divider,
                            divider_reached=should_run,
                            runtime_paused=runtime_control.is_paused(),
                            session_allowed=session_allowed,
                        )
                    if runtime_control.is_paused():
                        self._emit_agent_trigger_skipped(
                            event_val=event_val,
                            source=msg.source_agent_id,
                            reason="runtime_paused",
                            backlog_remaining=backlog_remaining,
                            trigger_age_ms=trigger_age_ms,
                        )
                        self._logger.debug("Runtime paused — skipping trigger", trigger=event_val)
                        continue
                    if not should_run:
                        self._emit_agent_trigger_skipped(
                            event_val=event_val,
                            source=msg.source_agent_id,
                            reason="divider_not_reached",
                            backlog_remaining=backlog_remaining,
                            trigger_age_ms=trigger_age_ms,
                        )
                        continue
                    if not session_allowed:
                        # The divider counter was already reset to 0 inside
                        # _should_run_for_trigger.  If the run was due (should_run=True)
                        # but the session rejected it, restore the counter to
                        # divider-1 so the very next trigger retries immediately
                        # instead of waiting a full divider cycle (<6> → <4> worst case).
                        if should_run and self._any_candle_divider > 1:
                            self._m5_candle_event_count = self._any_candle_divider - 1
                        self._logger.info(
                            "Trigger skipped — outside session filter",
                            trigger=event_val,
                            agent_id=self.agent_id,
                        )
                        continue
                    if self._run_lock.locked():
                        self._emit_agent_trigger_skipped(
                            event_val=event_val,
                            source=msg.source_agent_id,
                            reason="llm_busy",
                            backlog_remaining=backlog_remaining,
                            trigger_age_ms=trigger_age_ms,
                        )
                        continue
                    async with self._run_lock:
                        await self._run_cycle(
                            trigger=event_val,
                            payload=msg.payload,
                            source=msg.source_agent_id,
                            correlation_id=str(msg.id),
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.exception(
                    "Message loop error", error=str(exc)
                )
                self._emit_system_error(f"Message loop: {type(exc).__name__}: {exc}")

    # ── Core cycle ────────────────────────────────────────────────────────────

    async def _run_cycle(
        self,
        trigger: str,
        payload: dict[str, Any],
        source: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """One agent decision cycle (tool-use loop with LLM)."""
        if runtime_control.is_paused():
            if trigger == EventType.AGENT_QUERY.value and correlation_id:
                await self._bus.publish(AgentMessage(
                    event_type=EventType.AGENT_QUERY_RESPONSE,
                    source_agent_id=self.agent_id,
                    payload={
                        "response": "Runtime is currently suspended. Try again after continue.",
                        "agent_id": self.agent_id,
                    },
                    correlation_id=correlation_id,
                ))
            return

        if self._llm_service_id is None or self._tool_dispatcher is None:
            if trigger == EventType.AGENT_QUERY.value and correlation_id:
                await self._bus.publish(AgentMessage(
                    event_type=EventType.AGENT_QUERY_RESPONSE,
                    source_agent_id=self.agent_id,
                    payload={
                        "response": "Agent is not ready: LLM/tool dispatcher not initialized.",
                        "agent_id": self.agent_id,
                    },
                    correlation_id=correlation_id,
                ))
            return

        context = self._tool_dispatcher._context
        previous_pair = context.pair if context is not None else None
        cycle_pair = self._resolve_cycle_pair(trigger, payload)
        previous_cycle_extra: dict[str, Any] = {}
        decision_snapshot: dict[str, Any] | None = None
        if context is not None and cycle_pair:
            context.pair = cycle_pair

        # Build the user message for this cycle
        cycle_started = perf_counter()
        try:
            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

            # Detect analysis payload by content, not trigger name.
            # Any payload with a "response" field that parses to a dict
            # containing a valid "symbol" is treated as an analysis payload.
            # This works regardless of whether the trigger is analysis_result,
            # ec_output, or any future relay type.
            analysis_response: str | None = None
            _raw_response = payload.get("response")
            _parsed_response = (
                self._parse_json_object(_raw_response)
                if isinstance(_raw_response, str) and _raw_response.strip()
                else None
            )
            _is_analysis_trigger = (
                isinstance(_parsed_response, dict)
                and isinstance(_parsed_response.get("symbol"), str)
                and bool(_parsed_response.get("symbol", "").strip())
            )
            if _is_analysis_trigger:
                analysis_response = payload.get("response")
                analysis_object = (
                    self._parse_json_object(analysis_response)
                    if isinstance(analysis_response, str)
                    else None
                )
                if context is not None:
                    for key in (
                        "cycle_trigger",
                        "analysis_response_text",
                        "analysis_response_object",
                        "analysis_event_payload",
                        "analysis_source_agent_id",
                    ):
                        previous_cycle_extra[key] = context.extra.get(key)
                    context.extra["cycle_trigger"] = trigger
                    context.extra["analysis_response_text"] = analysis_response
                    context.extra["analysis_response_object"] = analysis_object
                    context.extra["analysis_event_payload"] = payload
                    context.extra["analysis_source_agent_id"] = source
                if self._is_broker_agent() and not isinstance(analysis_object, dict):
                    self._logger.warning(
                        "Skipping invalid analysis payload for broker agent",
                        agent_id=self.agent_id,
                        trigger=trigger,
                        source=source,
                    )
                    return

            # Build user_msg: agent_query always passes the question (interactive);
            # all other triggers only forward payload when pass_trigger=true
            chat_history: list[dict[str, Any]] | None = None
            if trigger == EventType.AGENT_QUERY.value:
                question = payload.get("question", "").strip()
                user_msg = (
                    f"[{now}] External query from {source or 'management_api'}:\n\n"
                    f"{question}"
                )
                raw_history = payload.get("history") or []
                if isinstance(raw_history, list) and raw_history:
                    chat_history = raw_history
            elif self._pass_trigger:
                if trigger == "timer":
                    user_msg = f"[{now}] Periodic analysis cycle. Review current market conditions and act if appropriate."
                elif _is_analysis_trigger:
                    # analysis_result and ec_output both carry the analysis JSON as "response"
                    user_msg = analysis_response if isinstance(analysis_response, str) and analysis_response.strip() else ""
                else:
                    user_msg = (
                        f"[{now}] Event received: {trigger}\n"
                        f"From: {source or 'system'}\n"
                        f"Details: {payload}"
                    )
            else:
                user_msg = ""

            snapshot_system_prompt: str | None = None
            if self._should_use_snapshot_context(trigger):
                if context is None or not cycle_pair:
                    self._logger.error(
                        "Snapshot runtime context missing broker/pair information",
                        agent_id=self.agent_id,
                        trigger=trigger,
                    )
                    self._emit_system_error("Snapshot runtime context missing broker/pair information.")
                    return
                snapshot_trigger_payload = self._snapshot_trigger_payload_for_cycle(trigger, payload)
                decision_snapshot, snapshot_errors = await build_analysis_snapshot(
                    broker_name=context.broker_name,
                    pair=cycle_pair,
                    trigger_payload=snapshot_trigger_payload,
                    profile=self._snapshot_profile_config,
                    strategy_aggressiveness=str(self._config.get("strategy_aggressiveness", "BALANCED")),
                    agent_id=self.agent_id,
                    repository=self._repository,
                    broker=None,
                    monitoring_bus=self._monitoring_bus,
                    event_bus=self._bus,
                )
                if snapshot_errors:
                    self._emit_analysis_snapshot_invalid(
                        trigger=trigger,
                        source=source,
                        snapshot=decision_snapshot,
                        errors=snapshot_errors,
                    )
                    self._logger.warning(
                        "Skipping AA cycle because market snapshot is invalid",
                        agent_id=self.agent_id,
                        trigger=trigger,
                        pair=cycle_pair,
                        errors=snapshot_errors,
                    )
                    return
                if decision_snapshot.get("cancel"):
                    cancel_reason = str(decision_snapshot.get("cancel_reason", "")).strip()
                    self._logger.info(
                        "Agent cycle cancelled by assembly script",
                        agent_id=self.agent_id,
                        pair=cycle_pair,
                        reason=cancel_reason or "no reason given",
                    )
                    return

                self._emit_analysis_snapshot_built(
                    trigger=trigger,
                    source=source,
                    snapshot=decision_snapshot,
                )
                snapshot_context = build_snapshot_user_message(
                    decision_snapshot,
                    self._snapshot_profile_config,
                )
                if user_msg.strip():
                    user_msg = f"{user_msg}\n\n{snapshot_context}"
                else:
                    user_msg = snapshot_context
                _base_prompt = (
                    _QUERY_BASE_SYSTEM_PROMPT
                    if trigger == EventType.AGENT_QUERY.value
                    else self._system_prompt
                )
                snapshot_system_prompt = build_snapshot_system_prompt(
                    _base_prompt,
                    self._decision_prompt_profile_config,
                    allow_tools=not self._should_use_snapshot_decision_engine(trigger),
                    snapshot=decision_snapshot,
                )

            # If no regular snapshot was built, optionally run the fallback snapshot
            # (used only for the selector script / placeholders — never forwarded as user message)
            if decision_snapshot is None and self._fallback_snapshot_profile_config and context is not None and cycle_pair:
                try:
                    fallback_snapshot, _ = await build_analysis_snapshot(
                        broker_name=context.broker_name,
                        pair=cycle_pair,
                        trigger_payload={},
                        profile=self._fallback_snapshot_profile_config,
                        strategy_aggressiveness=str(self._config.get("strategy_aggressiveness", "BALANCED")),
                        agent_id=self.agent_id,
                        repository=self._repository,
                        broker=None,
                        monitoring_bus=self._monitoring_bus,
                        event_bus=self._bus,
                    )
                except Exception as _fb_exc:
                    self._logger.warning(
                        "Decision prompt fallback snapshot failed",
                        agent_id=self.agent_id,
                        error=str(_fb_exc),
                    )
                    fallback_snapshot = None
            else:
                fallback_snapshot = None

            # Apply decision prompt profile even when no regular snapshot was built
            selector_snapshot = decision_snapshot if decision_snapshot is not None else fallback_snapshot
            if snapshot_system_prompt is None and self._decision_prompt_profile_config:
                _base_prompt = (
                    _QUERY_BASE_SYSTEM_PROMPT
                    if trigger == EventType.AGENT_QUERY.value
                    else self._system_prompt
                )
                snapshot_system_prompt = build_snapshot_system_prompt(
                    _base_prompt,
                    self._decision_prompt_profile_config,
                    allow_tools=True,
                    snapshot=selector_snapshot,
                )
            # For free queries with no snapshot/decision profile, still use neutral prompt
            if snapshot_system_prompt is None and trigger == EventType.AGENT_QUERY.value:
                snapshot_system_prompt = _QUERY_BASE_SYSTEM_PROMPT

            self._emit_agent_input_built(
                trigger=trigger,
                source=source,
                raw_payload=payload,
                derived_user_message=user_msg,
            )
            self._logger.debug("Starting cycle", trigger=trigger, pair=context.pair if context else None)
            try:
                if decision_snapshot is not None and self._should_use_snapshot_decision_engine(trigger):
                    final_text, total_tokens, executed_tool_names = await self._run_decision_only_cycle(
                        user_message=user_msg,
                        trigger=trigger,
                        source=source,
                        snapshot=decision_snapshot,
                    )
                else:
                    final_text, total_tokens, executed_tool_names = await self._run_with_tools(
                        user_msg,
                        trigger=trigger,
                        source=source,
                        correlation_id=correlation_id,
                        system_prompt_override=snapshot_system_prompt,
                        history=chat_history,
                    )
            except Exception as exc:
                self._logger.exception("Cycle failed", trigger=trigger, error=str(exc))
                self._emit_system_error(f"Cycle failed: {type(exc).__name__}: {exc}")
                if trigger == EventType.AGENT_QUERY.value and correlation_id:
                    await self._bus.publish(AgentMessage(
                        event_type=EventType.AGENT_QUERY_RESPONSE,
                        source_agent_id=self.agent_id,
                        payload={
                            "response": f"LLM cycle failed: {type(exc).__name__}: {exc}",
                            "agent_id": self.agent_id,
                        },
                        correlation_id=correlation_id,
                    ))
                return
            cycle_latency_ms = (perf_counter() - cycle_started) * 1000.0
            if cycle_latency_ms >= (_LONG_CYCLE_WARN_SECONDS * 1000.0):
                self._logger.warning(
                    "Long agent cycle detected",
                    trigger=trigger,
                    source=source,
                    pair=context.pair if context else None,
                    latency_ms=round(cycle_latency_ms, 1),
                )

            # For agent_query cycles: publish the LLM response back to the caller
            if trigger == EventType.AGENT_QUERY.value and correlation_id:
                await self._bus.publish(AgentMessage(
                    event_type=EventType.AGENT_QUERY_RESPONSE,
                    source_agent_id=self.agent_id,
                    payload={"response": final_text, "agent_id": self.agent_id},
                    correlation_id=correlation_id,
                ))
                return

            await self._execute_broker_decision_fallback(
                final_text=final_text,
                executed_tool_names=executed_tool_names,
            )

            if self._is_analysis_agent():
                if not final_text.strip():
                    self._logger.warning(
                        "Analysis agent produced empty final_text; suppressing analysis_result publish",
                        agent_id=self.agent_id,
                        trigger=trigger,
                    )
                    return
                analysis_timestamp = self._resolve_analysis_timestamp(trigger, payload)
                analysis_payload = {
                    "agent_id": self.agent_id,
                    "trigger": trigger,
                    "trigger_source": source,
                    "trigger_payload": payload,
                    "response": final_text,
                    "timestamp": analysis_timestamp,
                }
                await self._persist_analysis_result(
                    bus_payload=analysis_payload,
                    final_text=final_text,
                    trigger=trigger,
                    source=source,
                    correlation_id=correlation_id,
                    pair=cycle_pair,
                    total_tokens=total_tokens,
                    latency_ms=cycle_latency_ms,
                    market_snapshot=decision_snapshot,
                )
                self._maybe_accelerate_candle_counter(final_text, trigger)
                await self._bus.publish(AgentMessage(
                    event_type=EventType.ANALYSIS_RESULT,
                    source_agent_id=self.agent_id,
                    payload=analysis_payload,
                    correlation_id=correlation_id,
                ))
        finally:
            if context is not None:
                context.pair = previous_pair
                for key, previous_value in previous_cycle_extra.items():
                    if previous_value is None:
                        context.extra.pop(key, None)
                    else:
                        context.extra[key] = previous_value

    async def _run_with_tools(
        self,
        user_message: str,
        *,
        trigger: str,
        source: str | None = None,
        correlation_id: str | None = None,
        system_prompt_override: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> tuple[str, int, list[str]]:
        """LLM ↔ tool-use conversation loop. Returns (final_text, total_tokens, executed_tool_names)."""
        from openforexai.ports.llm import LLMResponseWithTools

        prior: list[dict[str, Any]] = [
            {"role": str(h.get("role", "user")), "content": str(h.get("content", ""))}
            for h in (history or [])
            if h.get("content", "")
        ]
        messages: list[dict[str, Any]] = prior + [{"role": "user", "content": user_message}]
        total_tokens = 0
        budget_tokens = 0
        final_text = ""
        executed_tool_names: list[str] = []

        effective_system_prompt = system_prompt_override or self._system_prompt

        for turn in range(self._max_tool_turns + 1):
            tool_specs = (
                self._tool_dispatcher.visible_specs(
                    used_tokens=budget_tokens, max_tokens=self._tool_context_budget_tokens
                )
                if self._tool_dispatcher is not None
                else []
            )

            self._emit_llm_request(messages, tool_specs, turn, system_prompt_override=effective_system_prompt)
            diagnostics_enabled = self._is_debug_diagnostics_enabled()
            self._configure_llm_debug_diagnostics(
                enabled=diagnostics_enabled,
                trigger=trigger,
                source=source,
                turn=turn,
                messages=messages,
                tools=tool_specs,
            )
            turn_started = perf_counter()
            if diagnostics_enabled:
                self._emit_llm_diagnostic_event(
                    MonitoringEventType.LLM_TURN_STARTED,
                    trigger=trigger,
                    source=source,
                    turn=turn,
                    message_count=len(messages),
                    tool_count=len(tool_specs),
                    approx_system_prompt_chars=len(effective_system_prompt),
                    approx_messages_chars=self._estimate_payload_chars(messages),
                    approx_tool_schema_chars=self._estimate_payload_chars(tool_specs),
                )
            try:
                response: LLMResponseWithTools = await llm_complete_with_tools(
                    event_bus        = self._bus,
                    llm_name         = self._llm_name or "",
                    source_id        = self.agent_id,
                    system_prompt    = effective_system_prompt,
                    messages         = messages,
                    tools            = tool_specs,
                    temperature      = self._llm_temperature,
                    max_tokens       = self._max_tokens,
                    reasoning_effort = self._llm_reasoning_effort,
                )
            except Exception as exc:
                self._emit_llm_error(
                    turn=turn, trigger=trigger, source=source,
                    error_type=type(exc).__name__, error=str(exc), call_mode="tools",
                )
                if diagnostics_enabled:
                    self._emit_llm_diagnostic_event(
                        MonitoringEventType.LLM_TURN_FAILED,
                        trigger=trigger,
                        source=source,
                        turn=turn,
                        message_count=len(messages),
                        tool_count=len(tool_specs),
                        elapsed_ms=round((perf_counter() - turn_started) * 1000.0, 1),
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                raise
            finally:
                self._configure_llm_debug_diagnostics(enabled=False)

            if diagnostics_enabled:
                self._emit_llm_diagnostic_event(
                    MonitoringEventType.LLM_TURN_COMPLETED,
                    trigger=trigger,
                    source=source,
                    turn=turn,
                    message_count=len(messages),
                    tool_count=len(tool_specs),
                    elapsed_ms=round((perf_counter() - turn_started) * 1000.0, 1),
                    stop_reason=response.stop_reason,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    tool_calls=len(response.tool_calls),
                )

            total_tokens += response.input_tokens + response.output_tokens
            final_text = response.content or ""
            self._emit_llm_monitoring(response, turn)

            if not response.wants_tools:
                break

            if turn >= self._max_tool_turns:
                self._logger.warning("Max tool turns reached", turns=self._max_tool_turns)
                break

            if self._tool_dispatcher is None:
                break

            tool_results = await self._tool_dispatcher.execute_all(
                tool_calls=response.tool_calls,
                used_tokens=budget_tokens,
                max_tokens=self._tool_context_budget_tokens,
            )
            executed_tool_names.extend(result.name for result in tool_results)

            # Build next-turn messages in canonical format.
            # The LLM Service handles provider-specific conversion internally.
            messages.append(self._build_assistant_turn(response))
            messages.append(self._build_tool_result_turn(tool_results))

            # Estimate next-turn context size from the current prompt plus the assistant turn.
            budget_tokens = max(response.input_tokens + response.output_tokens, 0)

        return final_text, total_tokens, executed_tool_names

    async def _run_decision_only_cycle(
        self,
        *,
        user_message: str,
        trigger: str,
        source: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> tuple[str, int, list[str]]:
        from openforexai.ports.llm import LLMResponse

        if self._llm_service_id is None:
            raise RuntimeError("LLM service is not initialized.")

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        tool_specs: list[dict[str, Any]] = []
        turn = 0
        self._emit_llm_request(messages, tool_specs, turn)
        diagnostics_enabled = self._is_debug_diagnostics_enabled()
        self._configure_llm_debug_diagnostics(
            enabled=diagnostics_enabled,
            trigger=trigger,
            source=source,
            turn=turn,
            messages=messages,
            tools=tool_specs,
        )
        turn_started = perf_counter()
        if diagnostics_enabled:
            self._emit_llm_diagnostic_event(
                MonitoringEventType.LLM_TURN_STARTED,
                trigger=trigger,
                source=source,
                turn=turn,
                message_count=1,
                tool_count=0,
                approx_system_prompt_chars=len(self._system_prompt),
                approx_messages_chars=self._estimate_payload_chars(messages),
                approx_tool_schema_chars=0,
                call_mode="decision_only",
            )
        try:
            response: LLMResponse = await llm_complete(
                event_bus        = self._bus,
                llm_name         = self._llm_name or "",
                source_id        = self.agent_id,
                system_prompt    = build_decision_only_system_prompt(
                    self._system_prompt,
                    self._decision_prompt_profile_config,
                    snapshot=snapshot,
                ),
                user_message     = user_message,
                temperature      = self._llm_temperature,
                max_tokens       = self._max_tokens,
                reasoning_effort = self._llm_reasoning_effort,
            )
        except Exception as exc:
            self._emit_llm_error(
                turn=turn, trigger=trigger, source=source,
                error_type=type(exc).__name__, error=str(exc), call_mode="decision_only",
            )
            if diagnostics_enabled:
                self._emit_llm_diagnostic_event(
                    MonitoringEventType.LLM_TURN_FAILED,
                    trigger=trigger,
                    source=source,
                    turn=turn,
                    message_count=1,
                    tool_count=0,
                    elapsed_ms=round((perf_counter() - turn_started) * 1000.0, 1),
                    error_type=type(exc).__name__,
                    error=str(exc),
                    call_mode="decision_only",
                )
            raise
        finally:
            self._configure_llm_debug_diagnostics(enabled=False)

        elapsed_ms = round((perf_counter() - turn_started) * 1000.0, 1)
        if diagnostics_enabled:
            self._emit_llm_diagnostic_event(
                MonitoringEventType.LLM_TURN_COMPLETED,
                trigger=trigger,
                source=source,
                turn=turn,
                message_count=1,
                tool_count=0,
                elapsed_ms=elapsed_ms,
                stop_reason="end_turn",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                tool_calls=0,
                call_mode="decision_only",
            )
        self._emit_llm_monitoring(response, turn)
        return response.content or "", response.input_tokens + response.output_tokens, []

    def _is_debug_diagnostics_enabled(self) -> bool:
        if self._monitoring_bus is None:
            return False
        return bool(getattr(self._monitoring_bus, "is_debug", False))

    def _configure_llm_debug_diagnostics(
        self,
        *,
        enabled: bool,
        trigger: str | None = None,
        source: str | None = None,
        turn: int | None = None,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        # HTTP-level diagnostics are now emitted by the LLMService on the bus.
        # The agent-side callback mechanism has been removed; this method is kept
        # as a no-op so call-sites don't need updating.
        return

    def _handle_llm_debug_diagnostic(self, event_name: str, payload: dict[str, Any]) -> None:
        mapping = {
            "llm_http_attempt_started": MonitoringEventType.LLM_HTTP_ATTEMPT_STARTED,
            "llm_http_attempt_completed": MonitoringEventType.LLM_HTTP_ATTEMPT_COMPLETED,
            "llm_http_attempt_failed": MonitoringEventType.LLM_HTTP_ATTEMPT_FAILED,
        }
        event_type = mapping.get(event_name)
        if event_type is None:
            return
        self._emit_llm_diagnostic_event(event_type, **payload)

    def _emit_llm_diagnostic_event(
        self,
        event_type: MonitoringEventType,
        **payload: Any,
    ) -> None:
        if not self._is_debug_diagnostics_enabled():
            return
        try:
            context = self._tool_dispatcher._context if self._tool_dispatcher is not None else None
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=event_type,
                broker_name=context.broker_name if context else None,
                pair=context.pair if context else None,
                payload={
                    "agent_id": self.agent_id,
                    **payload,
                },
            ))
        except Exception:
            pass

    def _emit_agent_trigger_received(
        self,
        *,
        event_val: str,
        source: str | None,
        backlog_remaining: int,
        trigger_age_ms: float | None,
    ) -> None:
        self._emit_agent_monitoring_event(
            MonitoringEventType.AGENT_TRIGGER_RECEIVED,
            trigger=event_val,
            source=source,
            backlog_remaining=backlog_remaining,
            trigger_age_ms=round(trigger_age_ms, 1) if trigger_age_ms is not None else None,
        )

    def _emit_agent_trigger_skipped(
        self,
        *,
        event_val: str,
        source: str | None,
        reason: str,
        backlog_remaining: int,
        trigger_age_ms: float | None,
    ) -> None:
        self._emit_agent_monitoring_event(
            MonitoringEventType.AGENT_TRIGGER_SKIPPED,
            trigger=event_val,
            source=source,
            reason=reason,
            backlog_remaining=backlog_remaining,
            trigger_age_ms=round(trigger_age_ms, 1) if trigger_age_ms is not None else None,
        )

    def _emit_agent_backlog_detected(
        self,
        *,
        event_val: str,
        source: str | None,
        backlog_remaining: int,
        trigger_age_ms: float | None,
    ) -> None:
        self._emit_agent_monitoring_event(
            MonitoringEventType.AGENT_BACKLOG_DETECTED,
            trigger=event_val,
            source=source,
            backlog_remaining=backlog_remaining,
            trigger_age_ms=round(trigger_age_ms, 1) if trigger_age_ms is not None else None,
        )

    def _emit_agent_monitoring_event(
        self,
        event_type: MonitoringEventType,
        **payload: Any,
    ) -> None:
        if not self._is_debug_diagnostics_enabled():
            return
        try:
            context = self._tool_dispatcher._context if self._tool_dispatcher is not None else None
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=event_type,
                broker_name=context.broker_name if context else None,
                pair=context.pair if context else None,
                payload={
                    "agent_id": self.agent_id,
                    **payload,
                },
            ))
        except Exception:
            pass

    @staticmethod
    def _measure_trigger_age_ms(event_val: str, payload: dict[str, Any]) -> float | None:
        if not isinstance(payload, dict):
            return None
        timestamp_value: str | None = None
        if event_val == EventType.M5_CANDLE_TRIGGER.value:
            candle = payload.get("candle")
            if isinstance(candle, dict):
                raw = candle.get("timestamp")
                if isinstance(raw, str) and raw.strip():
                    timestamp_value = raw
        elif event_val == EventType.ANALYSIS_RESULT.value:
            raw = payload.get("timestamp")
            if isinstance(raw, str) and raw.strip():
                timestamp_value = raw
        if not timestamp_value:
            return None
        try:
            trigger_ts = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return (datetime.now(UTC) - trigger_ts).total_seconds() * 1000.0

    @staticmethod
    def _estimate_payload_chars(value: Any) -> int:
        try:
            return len(json.dumps(value, default=str))
        except Exception:
            return 0

    # ── EventBus helpers ──────────────────────────────────────────────────────

    async def publish(self, message: AgentMessage) -> None:
        await self._bus.publish(message)

    async def _publish_m5_trigger_counter(
        self,
        *,
        payload: dict[str, Any],
        trigger_count: int,
        divider: int,
        divider_reached: bool,
        runtime_paused: bool,
        session_allowed: bool = True,
    ) -> None:
        if self._monitoring_bus is None:
            return
        candle = payload.get("candle") if isinstance(payload, dict) else None
        candle_timestamp = candle.get("timestamp") if isinstance(candle, dict) else None
        try:
            context = self._tool_dispatcher._context if self._tool_dispatcher is not None else None
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=EventType.M5_TRIGGER_COUNTER,
                broker_name=context.broker_name if context else None,
                pair=context.pair if context else None,
                payload={
                    "agent_id": self.agent_id,
                    "pair": payload.get("pair") if isinstance(payload, dict) else None,
                    "count": trigger_count,
                    "every": divider,
                    "due": divider_reached,
                    "paused": runtime_paused,
                    "session": session_allowed,
                    "run": divider_reached and not runtime_paused and session_allowed,
                    "ts": candle_timestamp,
                },
            ))
        except Exception:
            pass

    def _is_analysis_agent(self) -> bool:
        parsed = AgentId.try_parse(self.agent_id)
        return parsed is not None and parsed.type == "AA"

    def _is_broker_agent(self) -> bool:
        parsed = AgentId.try_parse(self.agent_id)
        return parsed is not None and parsed.type == "BA"

    def _resolve_cycle_pair(self, trigger: str, payload: dict[str, Any]) -> str | None:
        """Resolve the effective pair for the current cycle."""
        configured_pair = self._config.get("pair")
        if isinstance(configured_pair, str) and configured_pair.strip() and configured_pair.strip().upper() != "ALL___":
            return configured_pair.strip().upper()

        # Derive pair from payload content — independent of trigger name.
        # Any payload carrying an analysis JSON with a valid "symbol" field is accepted.
        analysis_response = payload.get("response")
        if isinstance(analysis_response, str) and analysis_response.strip():
            parsed_response = self._parse_json_object(analysis_response)
            if isinstance(parsed_response, dict):
                symbol = parsed_response.get("symbol")
                if isinstance(symbol, str) and symbol.strip():
                    return symbol.strip().upper()

        trigger_payload = payload.get("trigger_payload")
        if isinstance(trigger_payload, dict):
            pair = trigger_payload.get("pair")
            if isinstance(pair, str) and pair.strip():
                return pair.strip().upper()

        return None

    def _resolve_analysis_timestamp(self, trigger: str, payload: dict[str, Any]) -> str:
        """Resolve the exact candle timestamp for an AA analysis cycle."""
        if trigger != EventType.M5_CANDLE_TRIGGER.value:
            raise RuntimeError(
                f"Analysis timestamp resolution only supports candle-triggered AA cycles, got {trigger!r}"
            )

        candle = payload.get("candle")
        if not isinstance(candle, dict):
            raise RuntimeError("Analysis trigger payload missing candle object")

        candle_timestamp = candle.get("timestamp")
        if not isinstance(candle_timestamp, str) or not candle_timestamp.strip():
            raise RuntimeError("Analysis trigger candle missing timestamp")

        return candle_timestamp

    def _should_use_snapshot_decision_engine(self, trigger: str) -> bool:
        return (
            self._is_analysis_agent()
            and trigger == EventType.M5_CANDLE_TRIGGER.value
            and bool(self._snapshot_profile_config)
        )

    def _should_use_snapshot_context(self, trigger: str) -> bool:
        if not self._snapshot_profile_config:
            return False
        return trigger in {
            EventType.M5_CANDLE_TRIGGER.value,
            EventType.ANALYSIS_RESULT.value,
            EventType.AGENT_QUERY.value,
        }

    @staticmethod
    def _snapshot_trigger_payload_for_cycle(trigger: str, payload: dict[str, Any]) -> dict[str, Any]:
        if trigger == EventType.M5_CANDLE_TRIGGER.value and isinstance(payload, dict):
            return payload
        if trigger == EventType.ANALYSIS_RESULT.value and isinstance(payload, dict):
            upstream = payload.get("trigger_payload")
            if isinstance(upstream, dict):
                return upstream
        return {}

    async def _execute_broker_decision_fallback(
        self,
        *,
        final_text: str,
        executed_tool_names: list[str],
    ) -> None:
        """Execute structured BA trade decisions when the model stopped without a tool call."""
        if not self._is_broker_agent() or self._tool_dispatcher is None:
            return

        # If a trading tool already ran in this cycle, do nothing.
        if any(name in {"auto_place_order", "place_order", "close_position", "modify_order"} for name in executed_tool_names):
            return

        decision = self._parse_json_object(final_text)
        if not isinstance(decision, dict):
            return

        action_taken = str(decision.get("action_taken", "")).strip().upper()
        if action_taken != "AUTO_PLACE_ORDER":
            return

        order_direction_raw = str(decision.get("order_direction", "")).strip().lower()
        if order_direction_raw not in {"buy", "sell"}:
            return

        arguments: dict[str, Any] = {"direction": order_direction_raw}
        risk_pct = decision.get("risk_pct")
        if isinstance(risk_pct, (int, float)):
            arguments["risk_pct"] = float(risk_pct)
        confidence = decision.get("confidence")
        if isinstance(confidence, (int, float)):
            arguments["confidence"] = float(confidence)
        reasoning = decision.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            arguments["reasoning"] = reasoning.strip()

        from openforexai.ports.llm import ToolCall

        self._logger.info(
            "Broker decision fallback executing trading tool",
            agent_id=self.agent_id,
            tool_name="auto_place_order",
            direction=order_direction_raw,
        )
        await self._tool_dispatcher.execute_all(
            tool_calls=[
                ToolCall(
                    id=f"fallback-auto-place-{datetime.now(UTC).timestamp()}",
                    name="auto_place_order",
                    arguments=arguments,
                )
            ],
            used_tokens=0,
            max_tokens=self._tool_context_budget_tokens,
        )

    @staticmethod
    def _parse_json_object(raw_text: str) -> dict[str, Any] | None:
        text = raw_text.strip()
        if not text:
            return None
        candidates = [text]
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            candidates.append(text[first:last + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    async def _persist_analysis_result(
        self,
        *,
        bus_payload: dict[str, Any],
        final_text: str,
        trigger: str,
        source: str | None,
        correlation_id: str | None,
        pair: str | None,
        total_tokens: int,
        latency_ms: float,
        market_snapshot: dict[str, Any] | None = None,
    ) -> None:
        analysis_object = self._parse_json_object(final_text) if final_text.strip() else None
        decided_at_raw = bus_payload.get("timestamp")
        decided_at = (
            datetime.fromisoformat(decided_at_raw)
            if isinstance(decided_at_raw, str) and decided_at_raw.strip()
            else datetime.now(UTC)
        )
        output: dict[str, Any] = {
            "analysis_text": final_text,
            "analysis": analysis_object,
            "snapshot_profile": self._snapshot_profile_name,
            "decision_prompt_profile": self._decision_prompt_profile_name,
        }
        if isinstance(market_snapshot, dict):
            output["snapshot_schema_version"] = market_snapshot.get("snapshot_schema_version")
            output["snapshot_valid"] = bool(market_snapshot.get("market_data_valid"))
        if isinstance(analysis_object, dict):
            for key in (
                "symbol",
                "decision",
                "confidence",
                "order_start_signal",
                "order_start_quality",
                "entry_quality",
                "setup_type",
                "invalidation_level",
                "first_target",
                "analysis_summary",
                "conflict_flags",
                "CheckNextCandle",
            ):
                output[key] = analysis_object.get(key)
        decision = AgentDecision(
            agent_id=self.agent_id,
            agent_role=AgentRole.TECHNICAL_ANALYSIS,
            pair=pair or (analysis_object.get("symbol") if isinstance(analysis_object, dict) else None),
            decision_type="analysis_result",
            input_context={
                "trigger": trigger,
                "trigger_source": source,
                "correlation_id": correlation_id,
                "bus_payload": bus_payload,
                "market_snapshot": market_snapshot if isinstance(market_snapshot, dict) else None,
            },
            output=output,
            llm_model=str(self._config.get("llm", "")),
            tokens_used=total_tokens,
            latency_ms=latency_ms,
            decided_at=decided_at,
            market_snapshot=market_snapshot,
        )
        try:
            await self._repository.save_agent_decision(decision)
        except Exception as exc:
            self._logger.exception("Failed to persist analysis result", error=str(exc))
            self._emit_system_error(f"Persist analysis failed: {type(exc).__name__}: {exc}")

    def load_prompt(self, prompt: str) -> None:
        """Hot-swap the system prompt without restarting."""
        self._system_prompt = prompt
        self._logger.info("System prompt updated", chars=len(prompt))

    # ── Static message builders ───────────────────────────────────────────────

    @staticmethod
    def _build_assistant_turn(response) -> dict[str, Any]:
        content: list[dict] = []
        if response.content:
            content.append({"type": "text", "text": response.content})
        for tc in response.tool_calls:
            content.append({"type": "tool_use", "id": tc.id,
                            "name": tc.name, "input": tc.arguments})
        return {"role": "assistant", "content": content}

    @staticmethod
    def _build_tool_result_turn(tool_results: list) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.tool_call_id,
                 "content": r.content, "is_error": r.is_error}
                for r in tool_results
            ],
        }

    def _emit_system_error(self, message: str) -> None:
        """Emit a SYSTEM_ERROR to the MonitoringBus.  Never raises."""
        if self._monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.SYSTEM_ERROR,
                payload={"agent_id": self.agent_id, "message": message},
            ))
        except Exception:
            pass  # monitoring must never mask a real problem

    def _emit_llm_error(
        self,
        *,
        turn: int,
        trigger: str,
        source: str | None,
        error_type: str,
        error: str,
        call_mode: str = "tools",
    ) -> None:
        """Emit LLM_ERROR unconditionally (not gated on debug diagnostics).  Never raises."""
        if self._monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            context = self._tool_dispatcher._context if self._tool_dispatcher is not None else None
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.LLM_ERROR,
                broker_name=context.broker_name if context else None,
                pair=context.pair if context else None,
                payload={
                    "agent_id": self.agent_id,
                    "turn": turn,
                    "trigger": trigger,
                    "source": source,
                    "error_type": error_type,
                    "error": error,
                    "call_mode": call_mode,
                },
            ))
        except Exception:
            pass

    def _emit_agent_input_built(
        self,
        *,
        trigger: str,
        source: str | None,
        raw_payload: dict[str, Any],
        derived_user_message: str,
    ) -> None:
        """Emit the agent-core transformed user message built from an incoming trigger."""
        if self._monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType

            ctx = self._tool_dispatcher._context if self._tool_dispatcher is not None else None
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.AGENT_INPUT_BUILT,
                broker_name=ctx.broker_name if ctx else None,
                pair=ctx.pair if ctx else None,
                payload={
                    "agent_id": self.agent_id,
                    "trigger": trigger,
                    "source": source,
                    "raw_payload": raw_payload,
                    "derived_user_message": derived_user_message,
                },
            ))
        except Exception:
            pass

    def _emit_llm_request(
        self,
        messages: list,
        tool_specs: list,
        turn: int,
        *,
        system_prompt_override: str | None = None,
    ) -> None:
        """Emit LLM_REQUEST with COMPLETE prompt context before each API call.

        No truncation is applied — the full system prompt, complete message history,
        and full tool definitions are stored for audit/evidence purposes.
        """
        if self._monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            ctx = self._tool_dispatcher._context if self._tool_dispatcher else None

            effective_system_prompt = system_prompt_override or self._system_prompt
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.LLM_REQUEST,
                broker_name=ctx.broker_name if ctx else None,
                pair=ctx.pair if ctx else None,
                payload={
                    "turn": turn,
                    "system_prompt": effective_system_prompt,   # complete — no truncation
                    "messages": messages,                    # complete history — no truncation
                    "message_count": len(messages),
                    "tool_count": len(tool_specs),
                    "tool_names": [t.get("name", "") for t in tool_specs],
                    "tool_specs": tool_specs,                # complete definitions — no truncation
                },
            ))
        except Exception:
            pass

    def _emit_llm_monitoring(self, response, turn: int) -> None:
        """Emit LLM_RESPONSE with COMPLETE response data.

        No truncation is applied — the full response content and all tool call
        inputs are stored for audit/evidence purposes.
        """
        if self._tool_dispatcher is None:
            return
        ctx = self._tool_dispatcher._context
        if ctx.monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            content = response.content or ""   # complete — no truncation
            response_tool_calls = getattr(response, "tool_calls", [])
            tool_call_details = [
                {
                    "id":        tc.id,
                    "name":      tc.name,
                    "arguments": tc.arguments,  # complete inputs — no truncation
                }
                for tc in response_tool_calls
            ]
            ctx.monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.LLM_RESPONSE,
                broker_name=ctx.broker_name,
                pair=ctx.pair,
                payload={
                    "turn": turn,
                    "stop_reason": getattr(response, "stop_reason", "end_turn"),
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "tool_calls": len(response_tool_calls),
                    "tool_names": [tc.name for tc in response_tool_calls],
                    "tool_call_details": tool_call_details,  # complete — no truncation
                    "model": response.model,
                    "content": content,                      # complete — no truncation
                },
            ))
        except Exception:
            pass

    def _emit_analysis_snapshot_built(
        self,
        *,
        trigger: str,
        source: str | None,
        snapshot: dict[str, Any],
    ) -> None:
        self._emit_analysis_snapshot_event(
            MonitoringEventType.AGENT_DECISION_SNAPSHOT_BUILT,
            trigger=trigger,
            source=source,
            snapshot=snapshot,
        )

    def _emit_analysis_snapshot_invalid(
        self,
        *,
        trigger: str,
        source: str | None,
        snapshot: dict[str, Any],
        errors: list[str],
    ) -> None:
        self._emit_analysis_snapshot_event(
            MonitoringEventType.AGENT_DECISION_SNAPSHOT_INVALID,
            trigger=trigger,
            source=source,
            snapshot=snapshot,
            errors=errors,
        )

    def _emit_analysis_snapshot_event(
        self,
        event_type: MonitoringEventType,
        *,
        trigger: str,
        source: str | None,
        snapshot: dict[str, Any],
        errors: list[str] | None = None,
    ) -> None:
        if self._monitoring_bus is None:
            return
        try:
            ctx = self._tool_dispatcher._context if self._tool_dispatcher is not None else None
            payload = {
                "agent_id": self.agent_id,
                "trigger": trigger,
                "source": source,
                "snapshot_profile": self._snapshot_profile_name,
                "decision_prompt_profile": self._decision_prompt_profile_name,
                "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
                "market_data_valid": snapshot.get("market_data_valid"),
                "symbol": snapshot.get("symbol"),
                "timestamp": snapshot.get("timestamp"),
                "features": snapshot.get("features"),
                "flags": snapshot.get("flags"),
            }
            if errors:
                payload["errors"] = errors
            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=event_type,
                broker_name=ctx.broker_name if ctx else None,
                pair=ctx.pair if ctx else None,
                payload=payload,
            ))
        except Exception:
            pass



