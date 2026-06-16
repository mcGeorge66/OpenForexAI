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
from dataclasses import replace
from datetime import UTC
from typing import Any

from openforexai.ports.llm import ToolCall, ToolResult
from openforexai.registry.runtime_registry import RuntimeRegistry
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
        effective_context = self._context_for_call(effective_arguments)

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
            context=effective_context,
            tool_name=tc.name,
            agent=self._context.agent_id,
            arguments=effective_arguments,
        )
        try:
            raw_result = await tool.execute(effective_arguments, effective_context)
            content = json.dumps(raw_result, default=str)
            # No truncation — complete result stored for audit/evidence purposes
            self._emit_monitoring(
                "TOOL_CALL_COMPLETED",
                context=effective_context,
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
                "TOOL_CALL_FAILED",
                context=effective_context,
                tool_name=tc.name,
                agent=self._context.agent_id,
                error=str(exc),
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

        Uses the pending-future mechanism on the bus — no subscribe() needed.
        """
        import uuid

        from openforexai.models.messaging import AgentMessage, EventType

        bus = self._context.event_bus
        if bus is None:
            _log.warning("No event_bus in context — auto-approving supervisor tool call")
            return True, ""

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        approval_msg = AgentMessage(
            event_type=EventType.SIGNAL_GENERATED,
            source_agent_id=self._context.agent_id,
            payload={
                "tool_name": tc.name,
                "arguments": effective_arguments,
                "approval_requested": True,
            },
        )
        future_key = str(approval_msg.id)
        bus.register_response_future(future_key, future)
        await bus.publish(approval_msg)

        try:
            response = await asyncio.wait_for(future, timeout=15.0)
            approved = response.get("approved", False)
            reason = response.get("reason", "")
            return approved, reason
        except TimeoutError:
            return False, "Supervisor approval timed out"
        finally:
            bus.cancel_response_future(future_key)

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

    def _context_for_call(self, arguments: dict[str, Any]) -> ToolContext:
        broker_value = arguments.get("broker_name", arguments.get("broker"))
        pair_value = arguments.get("pair")

        broker_name = self._resolve_broker_name_override(broker_value)
        pair = self._resolve_pair_override(pair_value)

        if broker_name == self._context.broker_name and pair == self._context.pair:
            return self._context
        return replace(self._context, broker_name=broker_name, pair=pair)

    def _resolve_broker_name_override(self, broker_value: Any) -> str | None:
        if not isinstance(broker_value, str) or not broker_value.strip():
            return self._context.broker_name

        broker_key = broker_value.strip()
        try:
            broker_instance = RuntimeRegistry.get_broker(broker_key)
        except KeyError:
            return broker_key.upper()

        short_name = str(getattr(broker_instance, "short_name", "")).strip()
        return short_name.upper() if short_name else broker_key.upper()

    def _resolve_pair_override(self, pair_value: Any) -> str | None:
        if not isinstance(pair_value, str) or not pair_value.strip():
            return self._context.pair
        return pair_value.strip().upper()

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

    def _emit_monitoring(self, event_str: str, *, context: ToolContext | None = None, **kwargs) -> None:
        effective_context = context or self._context
        if effective_context.monitoring_bus is None:
            return
        try:
            from datetime import datetime

            from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
            try:
                mtype = MonitoringEventType[event_str]
            except KeyError:
                return
            effective_context.monitoring_bus.emit(MonitoringEvent(
                timestamp=datetime.now(UTC),
                source_module=f"tool_dispatcher:{effective_context.agent_id}",
                event_type=mtype,
                broker_name=effective_context.broker_name,
                pair=effective_context.pair,
                payload=kwargs,
            ))
        except Exception:
            pass
