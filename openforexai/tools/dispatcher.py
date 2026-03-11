"""ToolDispatcher — executes tool calls from the LLM in the agent context.

Responsibilities
----------------
1. Receives a list of ``ToolCall`` objects from ``LLMResponseWithTools``.
2. Looks up each tool in the ``ToolRegistry``.
3. Applies the **approval flow** (direct / supervisor / human).
4. Applies **context budget gating** — only allowed tools at each token tier.
5. Calls ``tool.execute(arguments, context)`` and wraps the result as a
   ``ToolResult``.
6. Emits ``MonitoringBus`` events for every tool call (start, success, error).

Context budget tiers (percentage of max_tokens used so far)
------------------------------------------------------------
Configured per-agent in ``agent_tools.json5``::

    "context_tiers": {
        "0":  ["*"],          // 0–69 %: all tools available
        "70": ["decision"],   // 70–89 %: only tools tagged "decision"
        "90": ["safety"]      // 90–100 %: only tools tagged "safety"
    }

Tool tags are set in ``agent_tools.json5`` under ``"tool_tags"``.

Approval modes
--------------
``"direct"``      Execute immediately (default).
``"supervisor"``  Publish event and wait for SIGNAL_APPROVED / SIGNAL_REJECTED.
``"human"``       Block until Management API provides approval (not yet impl.).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC
from typing import Any

from openforexai.ports.llm import ToolCall, ToolResult
from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.registry import ToolRegistry

_log = logging.getLogger(__name__)

# Default context tiers (fraction of budget used → allowed tool set key)
_DEFAULT_TIERS: list[tuple[float, str]] = [
    (0.90, "safety"),
    (0.70, "decision"),
    (0.00, "all"),
]


class ToolDispatcher:
    """Executes LLM-requested tool calls with approval and budget gating.

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

        # Context tiers: {"all": [...], "decision": [...], "safety": [...]}
        self._tier_tools: dict[str, list[str]] = self._config.get("tier_tools", {})

        # Raw tier thresholds from config
        raw_tiers = self._config.get("context_tiers", {})
        # Convert {"0": "all", "70": "decision", "90": "safety"} → sorted list
        self._tiers: list[tuple[float, str]] = sorted(
            [(float(k) / 100.0, v) for k, v in raw_tiers.items()],
            reverse=True,
        ) or _DEFAULT_TIERS

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
            used_tokens:   Tokens used so far in the current conversation.
            max_tokens:    Configured max_tokens for this agent.
        """
        budget_fraction = used_tokens / max(max_tokens, 1)
        active_tier = self._active_tier(budget_fraction)

        results: list[ToolResult] = []
        for tc in tool_calls:
            result = await self._execute_one(tc, active_tier)
            results.append(result)
        return results

    def visible_specs(
        self,
        used_tokens: int = 0,
        max_tokens: int = 4096,
    ) -> list[dict]:
        """Return ToolSpec list visible to the LLM at current budget level."""
        budget_fraction = used_tokens / max(max_tokens, 1)
        active_tier = self._active_tier(budget_fraction)
        allowed_names = self._tools_for_tier(active_tier)
        return self._registry.specs_for(allowed_names)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _execute_one(
        self,
        tc: ToolCall,
        active_tier: str,
    ) -> ToolResult:
        tool = self._registry.get(tc.name)

        # Unknown tool
        if tool is None:
            _log.warning("Agent %s called unknown tool %r", self._context.agent_id, tc.name)
            return ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=json.dumps({"error": f"Tool {tc.name!r} is not registered."}),
                is_error=True,
            )

        # Tier gate
        if not self._tool_allowed_in_tier(tc.name, active_tier):
            msg = (
                f"Tool {tc.name!r} is not available at the current context budget tier "
                f"({active_tier}). Use a simpler tool or proceed without tool call."
            )
            _log.debug(msg)
            return ToolResult(
                tool_call_id=tc.id,
                name=tc.name,
                content=json.dumps({"error": msg}),
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
            approved, reason = await self._check_approval(tc, tool, approval_mode)
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
            arguments=tc.arguments,
        )
        try:
            raw_result = await tool.execute(tc.arguments, self._context)
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
    ) -> tuple[bool, str]:
        if mode == "supervisor":
            return await self._supervisor_approval(tc, tool)
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
                "arguments": tc.arguments,
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

    # ── Budget tiers ──────────────────────────────────────────────────────────

    def _active_tier(self, budget_fraction: float) -> str:
        for threshold, tier_name in self._tiers:
            if budget_fraction >= threshold:
                return tier_name
        return "all"

    def _tools_for_tier(self, tier_name: str) -> list[str]:
        if not self._tier_tools:
            # No tier config — all registered tools are available
            return self._registry.all_names()
        tools = self._tier_tools.get(tier_name, [])
        if "*" in tools:
            return self._registry.all_names()
        return tools

    def _tool_allowed_in_tier(self, tool_name: str, tier_name: str) -> bool:
        allowed = self._tools_for_tier(tier_name)
        return tool_name in allowed or "*" in allowed

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

