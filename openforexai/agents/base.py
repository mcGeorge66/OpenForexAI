"""BaseAgent — lifecycle-aware async agent with native tool-use loop.

Every agent:
- Has a structured ``agent_id`` (format: BROKER_PAIR_TYPE_NAME)
- Holds references to an LLM provider, repository, event bus, and tool dispatcher
- Supports hot-swappable ``_system_prompt`` (used by OptimizationAgent)
- Implements ``run_cycle()`` for periodic or reactive logic
- Provides ``run_with_tools()`` for the full tool-use conversation loop
- Receives EventBus messages via personal queue → ``_handle_message()``

Tool-use loop
-------------
``run_with_tools()`` orchestrates the multi-turn LLM ↔ tool conversation::

    1. Call LLM with current messages + visible tool specs
    2. If LLM wants tools → execute via ToolDispatcher → append results → repeat
    3. Stop when LLM returns "end_turn", max_turns is reached, or budget exceeded
    4. Return the final text response

Queue-based message delivery
-----------------------------
``start()`` runs the cycle loop and a message loop concurrently (TaskGroup).
Override ``_handle_message()`` to react to specific ``EventType`` values.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider, LLMResponseWithTools
from openforexai.tools.dispatcher import ToolDispatcher
from openforexai.utils.logging import get_logger

_DEFAULT_MAX_TOOL_TURNS = 10


class BaseAgent(ABC):
    """Lifecycle-aware async agent base with native tool-use loop."""

    def __init__(
        self,
        agent_id: str,
        llm: AbstractLLMProvider,
        repository: AbstractRepository,
        bus: EventBus,
        tool_dispatcher: ToolDispatcher | None = None,
        max_tool_turns: int = _DEFAULT_MAX_TOOL_TURNS,
        max_tokens: int = 4096,
    ) -> None:
        self.agent_id = agent_id
        self.llm = llm
        self.repository = repository
        self.bus = bus
        self._tool_dispatcher = tool_dispatcher
        self._max_tool_turns = max_tool_turns
        self._max_tokens = max_tokens
        self._system_prompt: str = ""
        self._running = False
        self._logger = get_logger(self.__class__.__name__).bind(agent_id=agent_id)

        # Register with EventBus to receive queue-based routed messages
        self._inbox: asyncio.Queue[AgentMessage] = bus.register_agent(agent_id)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start cycle loop and message loop concurrently."""
        self._running = True
        await self._on_start()
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._run_cycle_loop())
                tg.create_task(self._run_message_loop())
        except* asyncio.CancelledError:
            pass
        finally:
            await self._on_stop()

    async def stop(self) -> None:
        self._running = False

    async def _on_start(self) -> None:
        """Override for one-time initialisation at agent startup."""

    async def _on_stop(self) -> None:
        """Override for cleanup at agent shutdown."""

    @abstractmethod
    async def run_cycle(self) -> None:
        """One iteration of the agent's decision or reaction logic."""

    # ── Internal loop runners ─────────────────────────────────────────────────

    async def _run_cycle_loop(self) -> None:
        while self._running:
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.exception("Unhandled error in run_cycle", error=str(exc))

    async def _run_message_loop(self) -> None:
        """Read from agent inbox (EventBus queue) and dispatch."""
        while self._running:
            try:
                message = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            try:
                await self._handle_message(message)
            except Exception as exc:
                self._logger.exception(
                    "Error handling message %s: %s", message.event_type, exc
                )

    async def _handle_message(self, message: AgentMessage) -> None:
        """Override to react to inbound EventBus queue messages."""

    # ── Prompt hot-swap ──────────────────────────────────────────────────────

    def load_prompt(self, prompt: str) -> None:
        """Replace the active system prompt without stopping the agent."""
        self._system_prompt = prompt
        self._logger.info("System prompt updated", chars=len(prompt))

    # ── Bus helpers ──────────────────────────────────────────────────────────

    async def publish(self, message: AgentMessage) -> None:
        await self.bus.publish(message)

    # ── Tool-use conversation loop ────────────────────────────────────────────

    async def run_with_tools(
        self,
        user_message: str,
        system_prompt: str | None = None,
        extra_messages: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> tuple[str, int]:
        """Run the full tool-use conversation loop.

        Returns ``(final_text, total_tokens_used)``.
        """
        prompt = system_prompt or self._system_prompt
        messages: list[dict[str, Any]] = list(extra_messages or [])
        messages.append({"role": "user", "content": user_message})

        total_tokens = 0
        final_text: str = ""

        for turn in range(self._max_tool_turns + 1):
            tool_specs = (
                self._tool_dispatcher.visible_specs(
                    used_tokens=total_tokens,
                    max_tokens=self._max_tokens,
                )
                if self._tool_dispatcher is not None
                else []
            )

            response: LLMResponseWithTools = await self.llm.complete_with_tools(
                system_prompt=prompt,
                messages=messages,
                tools=tool_specs,
                temperature=temperature,
                max_tokens=self._max_tokens,
            )

            total_tokens += response.input_tokens + response.output_tokens
            final_text = response.content or ""
            self._emit_llm_monitoring(response, turn)

            if not response.wants_tools:
                break

            if turn >= self._max_tool_turns:
                self._logger.warning("Max tool turns (%d) reached", self._max_tool_turns)
                break

            if self._tool_dispatcher is None:
                self._logger.error("LLM wants tools but no ToolDispatcher — stopping")
                break

            tool_results = await self._tool_dispatcher.execute_all(
                tool_calls=response.tool_calls,
                used_tokens=total_tokens,
                max_tokens=self._max_tokens,
            )

            if hasattr(self.llm, "assistant_message_with_tools"):
                messages.append(self.llm.assistant_message_with_tools(
                    response.content, response.tool_calls
                ))
                turn_result = self.llm.tool_result_message(tool_results)
                if isinstance(turn_result, list):
                    messages.extend(turn_result)
                else:
                    messages.append(turn_result)
            else:
                messages.append(self._build_assistant_turn(response))
                messages.append(self._build_tool_result_turn(tool_results))

        return final_text, total_tokens

    # ── Static message builders ───────────────────────────────────────────────

    @staticmethod
    def _build_assistant_turn(response: LLMResponseWithTools) -> dict[str, Any]:
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

    def _emit_llm_monitoring(self, response: LLMResponseWithTools, turn: int) -> None:
        if self._tool_dispatcher is None:
            return
        ctx = self._tool_dispatcher._context
        if ctx.monitoring_bus is None:
            return
        try:
            from datetime import datetime, timezone
            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            ctx.monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(timezone.utc),
                source_module=f"agent:{self.agent_id}",
                event_type=MonitoringEventType.LLM_RESPONSE,
                broker_name=ctx.broker_name,
                pair=ctx.pair,
                payload={"turn": turn, "stop_reason": response.stop_reason,
                         "input_tokens": response.input_tokens,
                         "output_tokens": response.output_tokens,
                         "tool_calls": len(response.tool_calls),
                         "model": response.model},
            ))
        except Exception:
            pass
