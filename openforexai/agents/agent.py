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
AnyCandle       int >= 1            Divider for m5_candle_available triggers
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
from datetime import UTC, datetime
from typing import Any

from openforexai.data.container import DataContainer
from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.ports.database import AbstractRepository
from openforexai.registry.runtime_registry import RuntimeRegistry
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
            cfg.get("AnyCandle", cfg.get("any_candle", _DEFAULT_ANY_CANDLE_DIVIDER))
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
        if isinstance(cfg.get("llm_params"), dict):
            llm_overrides.update(cfg["llm_params"])
        if isinstance(cfg.get("llm_config"), dict):
            llm_overrides.update(cfg["llm_config"])
        # Backward compatibility for any legacy top-level keys on agent config.
        for key in ("temperature", "max_tokens"):
            if key in cfg:
                llm_overrides[key] = cfg.get(key)

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

    def _should_run_for_trigger(self, event_val: str) -> bool:
        if event_val != EventType.M5_CANDLE_AVAILABLE.value:
            return True
        if self._any_candle_divider <= 1:
            return True
        self._m5_candle_event_count += 1
        if self._m5_candle_event_count % self._any_candle_divider != 0:
            self._logger.debug(
                "Skipping M5 trigger because AnyCandle divider not reached",
                any_candle=self._any_candle_divider,
                candle_count=self._m5_candle_event_count,
            )
            return False
        return True

    # ── Run loops ─────────────────────────────────────────────────────────────

    async def _run_timer_loop(self, interval: int) -> None:
        """Trigger run_cycle() every ``interval`` seconds.

        Fires immediately on first call so agents analyse on startup,
        then waits *interval* seconds between subsequent cycles.
        """
        first_run = True
        while self._running:
            if not first_run:
                await asyncio.sleep(interval)
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
                    if not self._should_run_for_trigger(event_val):
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

        # Build the user message for this cycle
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        if trigger == "timer":
            user_msg = f"[{now}] Periodic analysis cycle. Review current market conditions and act if appropriate."
        elif trigger == EventType.AGENT_QUERY.value:
            question = payload.get("question", "").strip()
            user_msg = (
                f"[{now}] External query from {source or 'management_api'}:\n\n"
                f"{question}"
            )
        else:
            user_msg = (
                f"[{now}] Event received: {trigger}\n"
                f"From: {source or 'system'}\n"
                f"Details: {payload}"
            )

        self._logger.debug("Starting cycle", trigger=trigger)
        try:
            final_text, _ = await self._run_with_tools(user_msg, correlation_id=correlation_id)
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

    async def _run_with_tools(
        self,
        user_message: str,
        correlation_id: str | None = None,
    ) -> tuple[str, int]:
        """LLM ↔ tool-use conversation loop.  Returns (final_text, total_tokens)."""
        from openforexai.ports.llm import LLMResponseWithTools

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        total_tokens = 0
        final_text = ""

        for turn in range(self._max_tool_turns + 1):
            tool_specs = (
                self._tool_dispatcher.visible_specs(
                    used_tokens=total_tokens, max_tokens=self._max_tokens
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
                used_tokens=total_tokens,
                max_tokens=self._max_tokens,
            )

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

        return final_text, total_tokens

    # ── EventBus helpers ──────────────────────────────────────────────────────

    async def publish(self, message: AgentMessage) -> None:
        await self._bus.publish(message)

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


