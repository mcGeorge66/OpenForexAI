"""ToolDispatcher — executes tool calls from the LLM in the agent context.

Responsibilities
----------------
1. Receives a list of ``ToolCall`` objects from ``LLMResponseWithTools``.
2. Looks up each tool in the ``ToolRegistry``.
3. Applies the **approval flow** (direct / supervisor / human).
4. Calls ``tool.execute(arguments, context)`` and wraps the result as a
   ``ToolResult``.
5. Emits ``MonitoringBus`` events for every tool call (start, success, error).

Approval modes
--------------
``"direct"``      Execute immediately (default).
``"supervisor"``  Publish event and wait for SIGNAL_APPROVED / SIGNAL_REJECTED.
``"human"``       Block until Management API provides approval (not yet impl.).
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
from datetime import UTC
from typing import Any

from openforexai.ports.llm import ToolCall, ToolResult
from openforexai.tools.argument_templates import (
    build_agent_placeholder_values,
    resolve_argument_templates,
)
from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.registry import ToolRegistry

_log = logging.getLogger(__name__)


class ToolDispatcher:
    """Executes LLM-requested tool calls with approval gating.

    Instantiate once per agent; configure via ``AgentToolConfig``.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        context: ToolContext,
        agent_tool_config: dict[str, Any] | None = None,
    ) -> None:
        self._registry = registry
        self._context = context
        self._config = agent_tool_config or {}

        # Allowed tool names for this agent (empty list = all registered)
        self._allowed: set[str] = set(self._config.get("allowed_tools", []))

        # Per-tool approval mode overrides: {"place_order": "supervisor"}
        self._approval_overrides: dict[str, str] = self._config.get("approval_modes", {})

        # Per-tool non-overridable argument values:
        # {"place_order": {"risk_pct": 0.5}, "ask_ga_market_outlook": {"agent": "..."}}
        raw_forced_arguments = self._config.get("forced_arguments", {})
        self._forced_arguments: dict[str, dict[str, Any]] = {}
        if isinstance(raw_forced_arguments, dict):
            for tool_name, forced_args in raw_forced_arguments.items():
                if isinstance(tool_name, str) and isinstance(forced_args, dict):
                    self._forced_arguments[tool_name] = dict(forced_args)

    # ── Public API ────────────────────────────────────────────────────────────

    async def execute_all(
        self,
        tool_calls: list[ToolCall],
        used_tokens: int = 0,
        max_tokens: int = 4096,
    ) -> list[ToolResult]:
        """Execute all tool calls and return results in the same order.

        Args:
            tool_calls:    Tool calls from ``LLMResponseWithTools.tool_calls``.
            used_tokens:   Unused compatibility parameter.
            max_tokens:    Unused compatibility parameter.
        """
        results: list[ToolResult] = []
        for tc in tool_calls:
            result = await self._execute_one(tc)
            results.append(result)
        return results

    def visible_specs(
        self,
        used_tokens: int = 0,
        max_tokens: int = 4096,
    ) -> list[dict]:
        """Return ToolSpec list visible to the LLM for this agent."""
        del used_tokens, max_tokens
        allowed_names = self._allowed_names()
        specs: list[dict[str, Any]] = []
        for name in allowed_names:
            tool = self._registry.get(name)
            if tool is None:
                continue
            specs.append(self._spec_with_forced_arguments_hidden(tool))
        return specs

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _execute_one(
        self,
        tc: ToolCall,
    ) -> ToolResult:
        tool = self._registry.get(tc.name)
        effective_arguments = self._merged_arguments(tc.name, tc.arguments)

        # Unknown tool
        if tool is None:
            _log.warning("Agent %s called unknown tool %r", self._context.agent_id, tc.name)
            return ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=json.dumps({"error": f"Tool {tc.name!r} is not registered."}),
                is_error=True,
            )

        # Agent-level allow list (empty = all allowed)
        if self._allowed and tc.name not in self._allowed:
            msg = f"Tool {tc.name!r} is not in the allowed list for this agent."
            return ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=json.dumps({"error": msg}),
                is_error=True,
            )

        # Approval flow
        approval_mode = self._approval_overrides.get(
            tc.name, tool.default_approval_mode if tool.requires_approval else "direct"
        )
        if approval_mode != "direct":
            approved, reason = await self._check_approval(tc, tool, approval_mode, effective_arguments)
            if not approved:
                return ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps({"error": f"Tool call rejected: {reason}"}),
                    is_error=True,
                )

        # Execute
        self._emit_monitoring(
            "TOOL_CALL_STARTED",
            tool_name=tc.name,
            agent=self._context.agent_id,
            arguments=effective_arguments,
        )
        try:
            raw_result = await tool.execute(effective_arguments, self._context)
            content = json.dumps(raw_result, default=str)
            # No truncation — complete result stored for audit/evidence purposes
            self._emit_monitoring(
                "TOOL_CALL_COMPLETED",
                tool_name=tc.name,
                agent=self._context.agent_id,
                result=content,               # complete — no truncation
                result_length=len(content),   # metric: how large the result is
            )
            return ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=content,
                is_error=False,
            )
        except Exception as exc:
            _log.exception("Tool %r raised: %s", tc.name, exc)
            self._emit_monitoring(
                "TOOL_CALL_FAILED", tool_name=tc.name, agent=self._context.agent_id, error=str(exc)
            )
            return ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=json.dumps({"error": str(exc)}),
                is_error=True,
            )

    # ── Approval ──────────────────────────────────────────────────────────────

    async def _check_approval(
        self,
        tc: ToolCall,
        tool: BaseTool,
        mode: str,
        effective_arguments: dict[str, Any],
    ) -> tuple[bool, str]:
        if mode == "supervisor":
            return await self._supervisor_approval(tc, tool, effective_arguments)
        if mode == "human":
            # Human approval not yet implemented — log and reject
            _log.warning(
                "Human approval required for tool %r but not yet implemented — rejecting",
                tc.name,
            )
            return False, "Human approval not yet implemented"
        return True, ""

    async def _supervisor_approval(
        self,
        tc: ToolCall,
        tool: BaseTool,
        effective_arguments: dict[str, Any],
    ) -> tuple[bool, str]:
        """Publish a SIGNAL_GENERATED event and wait for SIGNAL_APPROVED/REJECTED.

        This leverages the existing supervisor flow; the arguments are included
        in the payload so the SupervisorAgent can run its risk checks.
        """
        import uuid

        from openforexai.models.messaging import AgentMessage, EventType

        if self._context.event_bus is None:
            _log.warning("No event_bus in context — auto-approving supervisor tool call")
            return True, ""

        correlation_id = str(uuid.uuid4())
        approval_event = asyncio.Event()
        result: dict[str, Any] = {}

        async def _on_decision(msg: AgentMessage) -> None:
            if msg.correlation_id != correlation_id:
                return
            result["approved"] = (msg.event_type == EventType.SIGNAL_APPROVED)
            result["reason"] = msg.payload.get("reason", "")
            approval_event.set()

        bus = self._context.event_bus
        bus.subscribe(EventType.SIGNAL_APPROVED, _on_decision)
        bus.subscribe(EventType.SIGNAL_REJECTED, _on_decision)

        await bus.publish(AgentMessage(
            event_type=EventType.SIGNAL_GENERATED,
            source_agent_id=self._context.agent_id,
            payload={
                "tool_name": tc.name,
                "arguments": effective_arguments,
                "approval_requested": True,
            },
            correlation_id=correlation_id,
        ))

        try:
            await asyncio.wait_for(approval_event.wait(), timeout=15.0)
        except TimeoutError:
            return False, "Supervisor approval timed out"
        finally:
            bus.unsubscribe(EventType.SIGNAL_APPROVED, _on_decision)
            bus.unsubscribe(EventType.SIGNAL_REJECTED, _on_decision)

        return result.get("approved", False), result.get("reason", "")

    def _allowed_names(self) -> list[str]:
        if self._allowed:
            return [name for name in self._registry.all_names() if name in self._allowed]
        return self._registry.all_names()

    def _merged_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(arguments or {})
        agent_config = self._context.extra.get("agent_config", {})
        placeholders = build_agent_placeholder_values(
            agent_id=self._context.agent_id,
            agent_config=agent_config if isinstance(agent_config, dict) else None,
            broker_name=self._context.broker_name,
            pair=self._context.pair,
        )
        forced = resolve_argument_templates(self._forced_arguments.get(tool_name, {}), placeholders)
        if forced:
            merged.update(forced)
        return merged

    def _spec_with_forced_arguments_hidden(self, tool: BaseTool) -> dict[str, Any]:
        spec = copy.deepcopy(tool.to_spec())
        forced = self._forced_arguments.get(tool.name, {})
        if not forced:
            return spec

        schema = spec.get("input_schema")
        if not isinstance(schema, dict):
            return spec

        properties = schema.get("properties")
        if isinstance(properties, dict):
            for arg_name in list(forced):
                properties.pop(arg_name, None)

        required = schema.get("required")
        if isinstance(required, list):
            schema["required"] = [arg_name for arg_name in required if arg_name not in forced]

        forced_list = ", ".join(sorted(forced))
        if forced_list:
            suffix = f" Fixed by agent config: {forced_list}."
            description = spec.get("description")
            spec["description"] = f"{description}{suffix}" if isinstance(description, str) else suffix.strip()

        return spec

    # ── Monitoring ────────────────────────────────────────────────────────────

    def _emit_monitoring(self, event_str: str, **kwargs) -> None:
        if self._context.monitoring_bus is None:
            return
        try:
            from datetime import datetime

            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            try:
                mtype = MonitoringEventType[event_str]
            except KeyError:
                return
            self._context.monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"tool_dispatcher:{self._context.agent_id}",
                event_type=mtype,
                broker_name=self._context.broker_name,
                pair=self._context.pair,
                payload=kwargs,
            ))
        except Exception:
            pass

