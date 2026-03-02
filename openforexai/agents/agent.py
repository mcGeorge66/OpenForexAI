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

Config keys (from system.json ``agents.<agent_id>``)
-----------------------------------------------------
llm              str                 LLM module name (RuntimeRegistry key)
broker           str | None          Broker module name — omit for GA agents
pair             str | None          Currency pair — AA agents only
timer            {enabled, interval} Periodic self-activation
event_triggers   list[str]           EventType values that wake the agent
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
from datetime import datetime, timezone
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
        self._apply_config(config_payload)
        self._logger.info("Config received — agent initialised")

        # Phase 4: run
        self._running = True
        timer_cfg = self._config.get("timer", {})

        async with asyncio.TaskGroup() as tg:
            if timer_cfg.get("enabled"):
                tg.create_task(
                    self._run_timer_loop(timer_cfg.get("interval_seconds", 300)),
                    name=f"{self.agent_id}:timer",
                )
            tg.create_task(self._run_message_loop(), name=f"{self.agent_id}:messages")

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
            except asyncio.TimeoutError:
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

        tool_cfg = cfg.get("tool_config", {})
        self._max_tool_turns = tool_cfg.get("max_tool_turns", _DEFAULT_MAX_TOOL_TURNS)
        self._max_tokens = tool_cfg.get("max_tokens", 4096)

        # LLM
        llm_name = cfg.get("llm")
        if llm_name:
            self._llm = RuntimeRegistry.get_llm(llm_name)

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

    async def _run_message_loop(self) -> None:
        """Deliver EventBus messages; invoke run_cycle for trigger events."""
        while self._running:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

            event_val = (
                msg.event_type.value
                if hasattr(msg.event_type, "value")
                else str(msg.event_type)
            )

            if event_val in self._event_triggers:
                try:
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
                        "Message cycle error", event=event_val, error=str(exc)
                    )

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
            return

        # Build the user message for this cycle
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if trigger == "timer":
            user_msg = f"[{now}] Periodic analysis cycle. Review current market conditions and act if appropriate."
        else:
            user_msg = (
                f"[{now}] Event received: {trigger}\n"
                f"From: {source or 'system'}\n"
                f"Details: {payload}"
            )

        self._logger.debug("Starting cycle", trigger=trigger)
        await self._run_with_tools(user_msg, correlation_id=correlation_id)

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

            response: LLMResponseWithTools = await self._llm.complete_with_tools(
                system_prompt=self._system_prompt,
                messages=messages,
                tools=tool_specs,
                temperature=0.1,
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

    def _emit_llm_monitoring(self, response, turn: int) -> None:
        if self._tool_dispatcher is None:
            return
        ctx = self._tool_dispatcher._context
        if ctx.monitoring_bus is None:
            return
        try:
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            ctx.monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(timezone.utc),
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
                    "model": response.model,
                },
            ))
        except Exception:
            pass
