"""Agent — the single, fully parameterised agent class for OpenForexAI.

All agent types (AA, BA, GA) use this class.  The difference between types is
exclusively determined by config and system prompt — not by code.

Bootstrap sequence
------------------
1. Agent is created with only ``(agent_id, bus, data_container, repository)``.
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
AnyCandle       int >= 1            Divider for m5_agent_trigger triggers
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

from openforexai.data.container import DataContainer
from openforexai.messaging.agent_id import AgentId
from openforexai.messaging.bus import EventBus
from openforexai.models.agent import AgentDecision, AgentRole
from openforexai.models.messaging import AgentMessage, EventType
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


class Agent:
    """Single parameterised agent — AA, BA, or GA.

    The type is cosmetic at runtime; only the config determines behaviour.
    """

    def __init__(
        self,
        agent_id: str,
        bus: EventBus,
        data_container: DataContainer,
        repository: AbstractRepository,
        monitoring_bus=None,
    ) -> None:
        self.agent_id = agent_id
        self._bus = bus
        self._data_container = data_container
        self._repository = repository
        self._monitoring_bus = monitoring_bus

        self._inbox: asyncio.Queue[AgentMessage] = bus.register_agent(agent_id)
        self._running = False
        self._logger = get_logger(self.__class__.__name__).bind(agent_id=agent_id)

        # Populated after config is received
        self._config: dict[str, Any] = {}
        self._system_prompt: str = ""
        self._event_triggers: set[str] = set()
        self._llm = None
        self._broker = None
        self._tool_dispatcher: ToolDispatcher | None = None
        self._max_tool_turns: int = _DEFAULT_MAX_TOOL_TURNS
        self._max_tokens: int = 4096
        self._tool_context_budget_tokens: int = 32768
        self._llm_temperature: float | None = None
        self._any_candle_divider: int = _DEFAULT_ANY_CANDLE_DIVIDER
        self._m5_candle_event_count: int = 0

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

        tool_cfg = cfg.get("tool_config", {})
        self._max_tool_turns = tool_cfg.get("max_tool_turns", _DEFAULT_MAX_TOOL_TURNS)

        # LLM
        llm_name = cfg.get("llm")
        if llm_name:
            self._llm = RuntimeRegistry.get_llm(llm_name)

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

        resolved_llm_max = resolved_llm.get("max_tokens")
        llm_default_max = getattr(self._llm, "default_max_tokens", None) if self._llm is not None else None

        tool_budget_max = tool_cfg.get("max_tokens")
        if isinstance(tool_budget_max, int) and tool_budget_max > 0:
            self._max_tokens = tool_budget_max
        elif isinstance(resolved_llm_max, int) and resolved_llm_max > 0:
            self._max_tokens = resolved_llm_max
        elif isinstance(llm_default_max, int) and llm_default_max > 0:
            self._max_tokens = llm_default_max

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
        if self._llm is not None:
            context = ToolContext(
                agent_id=self.agent_id,
                broker_name=runtime_broker_name,
                pair=cfg.get("pair"),
                data_container=self._data_container,
                repository=self._repository,
                broker=self._broker,
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
        if event_val != EventType.M5_AGENT_TRIGGER.value:
            return True, None
        self._m5_candle_event_count += 1
        trigger_count = self._m5_candle_event_count
        if self._any_candle_divider <= 1:
            return True, trigger_count
        if trigger_count % self._any_candle_divider != 0:
            self._logger.debug(
                "Skipping M5 trigger because AnyCandle divider not reached",
                any_candle=self._any_candle_divider,
                candle_count=trigger_count,
            )
            return False, trigger_count
        return True, trigger_count

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
                event_val = (
                    msg.event_type.value
                    if hasattr(msg.event_type, "value")
                    else str(msg.event_type)
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
                        correlation_id=msg.correlation_id,
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
                    if event_val == EventType.M5_AGENT_TRIGGER.value:
                        await self._publish_m5_trigger_counter(
                            payload=msg.payload,
                            trigger_count=trigger_count or 0,
                            divider=self._any_candle_divider,
                            divider_reached=should_run,
                            runtime_paused=runtime_control.is_paused(),
                        )
                    if runtime_control.is_paused():
                        self._logger.debug("Runtime paused — skipping trigger", trigger=event_val)
                        continue
                    if not should_run:
                        continue
                    await self._run_cycle(
                        trigger=event_val,
                        payload=msg.payload,
                        source=msg.source_agent_id,
                        correlation_id=msg.correlation_id,
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

        if self._llm is None or self._tool_dispatcher is None:
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
        if context is not None and cycle_pair:
            context.pair = cycle_pair

        # Build the user message for this cycle
        try:
            cycle_started = perf_counter()
            now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            if trigger == "timer":
                user_msg = f"[{now}] Periodic analysis cycle. Review current market conditions and act if appropriate."
            elif trigger == EventType.AGENT_QUERY.value:
                question = payload.get("question", "").strip()
                user_msg = (
                    f"[{now}] External query from {source or 'management_api'}:\n\n"
                    f"{question}"
                )
            elif trigger == EventType.ANALYSIS_RESULT.value:
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
                        "Skipping invalid analysis_result payload for broker agent",
                        agent_id=self.agent_id,
                        source=source,
                    )
                    return
                if isinstance(analysis_response, str) and analysis_response.strip():
                    user_msg = analysis_response
                else:
                    user_msg = ""
            else:
                user_msg = (
                    f"[{now}] Event received: {trigger}\n"
                    f"From: {source or 'system'}\n"
                    f"Details: {payload}"
                )

            self._emit_agent_input_built(
                trigger=trigger,
                source=source,
                raw_payload=payload,
                derived_user_message=user_msg,
            )
            self._logger.debug("Starting cycle", trigger=trigger, pair=context.pair if context else None)
            try:
                final_text, total_tokens, executed_tool_names = await self._run_with_tools(
                    user_msg,
                    correlation_id=correlation_id,
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
                    latency_ms=(perf_counter() - cycle_started) * 1000.0,
                )
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
        correlation_id: str | None = None,
    ) -> tuple[str, int, list[str]]:
        """LLM ↔ tool-use conversation loop. Returns (final_text, total_tokens, executed_tool_names)."""
        from openforexai.ports.llm import LLMResponseWithTools

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        total_tokens = 0
        budget_tokens = 0
        final_text = ""
        executed_tool_names: list[str] = []

        for turn in range(self._max_tool_turns + 1):
            tool_specs = (
                self._tool_dispatcher.visible_specs(
                    used_tokens=budget_tokens, max_tokens=self._tool_context_budget_tokens
                )
                if self._tool_dispatcher is not None
                else []
            )

            self._emit_llm_request(messages, tool_specs, turn)
            response: LLMResponseWithTools = await self._llm.complete_with_tools(
                system_prompt=self._system_prompt,
                messages=messages,
                tools=tool_specs,
                temperature=self._llm_temperature,
                max_tokens=self._max_tokens,
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

            if hasattr(self._llm, "assistant_message_with_tools"):
                messages.append(
                    self._llm.assistant_message_with_tools(response.content, response.tool_calls)
                )
                turn_result = self._llm.tool_result_message(tool_results)
                if isinstance(turn_result, list):
                    messages.extend(turn_result)
                else:
                    messages.append(turn_result)
            else:
                messages.append(self._build_assistant_turn(response))
                messages.append(self._build_tool_result_turn(tool_results))

            # Estimate next-turn context size from the current prompt plus the assistant turn.
            budget_tokens = max(response.input_tokens + response.output_tokens, 0)

        return final_text, total_tokens, executed_tool_names

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
    ) -> None:
        candle = payload.get("candle") if isinstance(payload, dict) else None
        candle_timestamp = candle.get("timestamp") if isinstance(candle, dict) else None
        await self._bus.publish(AgentMessage(
            event_type=EventType.M5_TRIGGER_COUNTER,
            source_agent_id=self.agent_id,
            payload={
                "pair": payload.get("pair") if isinstance(payload, dict) else None,
                "count": trigger_count,
                "every": divider,
                "due": divider_reached,
                "paused": runtime_paused,
                "run": divider_reached and not runtime_paused,
                "ts": candle_timestamp,
            },
        ))

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

        if trigger != EventType.ANALYSIS_RESULT.value:
            return None

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
        if trigger != EventType.M5_AGENT_TRIGGER.value:
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
        }
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
            },
            output=output,
            llm_model=str(self._config.get("llm", "")),
            tokens_used=total_tokens,
            latency_ms=latency_ms,
            decided_at=decided_at,
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

    def _emit_llm_request(self, messages: list, tool_specs: list, turn: int) -> None:
        """Emit LLM_REQUEST with COMPLETE prompt context before each API call.

        No truncation is applied — the full system prompt, complete message history,
        and full tool definitions are stored for audit/evidence purposes.
        """
        if self._monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            ctx = self._tool_dispatcher._context if self._tool_dispatcher else None

            self._monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.LLM_REQUEST,
                broker_name=ctx.broker_name if ctx else None,
                pair=ctx.pair if ctx else None,
                payload={
                    "turn": turn,
                    "system_prompt": self._system_prompt,   # complete — no truncation
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
            tool_call_details = [
                {
                    "id":        tc.id,
                    "name":      tc.name,
                    "arguments": tc.arguments,  # complete inputs — no truncation
                }
                for tc in response.tool_calls
            ]
            ctx.monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.LLM_RESPONSE,
                broker_name=ctx.broker_name,
                pair=ctx.pair,
                payload={
                    "turn": turn,
                    "stop_reason": response.stop_reason,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "tool_calls": len(response.tool_calls),
                    "tool_names": [tc.name for tc in response.tool_calls],
                    "tool_call_details": tool_call_details,  # complete — no truncation
                    "model": response.model,
                    "content": content,                      # complete — no truncation
                },
            ))
        except Exception:
            pass



