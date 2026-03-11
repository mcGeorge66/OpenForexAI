"""AgentBridgeTool — config-driven inter-agent communication via AGENT_QUERY.

Concept
-------
Each AgentBridgeTool instance represents a named, LLM-callable tool that
internally routes the call to another running agent via the EventBus.

From the LLM's perspective it is identical to any other tool — it has a name,
a description, and accepts a ``question`` argument. The LLM does not know (and
does not need to know) that a second agent is being invoked.

From the architecture's perspective the agents remain fully decoupled:
- The calling agent only sees tools in its manifest.
- The target agent only sees an ``AGENT_QUERY`` event.
- No code change in either agent is required.

Configuration (``config/RunTime/agent_tools.json5``)
----------------------------------------------------
Classic single-target form (unchanged)::

    {
      "bridge_tools": [
        {
          "name": "ask_ga_market_outlook",
          "description": "Ask GA for market outlook",
          "target_agent_id": "GLOBL-ALL___-GA-TA001",
          "timeout_seconds": 90,
          "question_description": "Specific question..."
        }
      ]
    }

New grouped multi-target form (one config entry -> multiple tool functions)::

    {
      "bridge_tools": [
        {
          "name": "ask_specialist",
          "targets": [
            {
              "tool_name": "ask_news_agent",
              "description": "Ask the news specialist for macro/news impact.",
              "target_agent_id": "GLOBL-ALL___-GA-NEWS1"
            },
            {
              "tool_name": "ask_ta_agent",
              "description": "Ask the technical-analysis specialist.",
              "target_agent_id": "GLOBL-ALL___-GA-TA001"
            }
          ],
          "timeout_seconds": 90,
          "question_description": "Specific question..."
        }
      ]
    }

Each target entry becomes its own registered AgentBridgeTool.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.tools.base import BaseTool, ToolContext

_log = logging.getLogger(__name__)

_DEFAULT_QUESTION_DESC = (
    "Your specific question or request. "
    "Be precise to get a focused answer."
)


class AgentBridgeTool(BaseTool):
    """Config-driven tool that bridges LLM tool calls to another agent.

    Create instances via :meth:`from_config` or the constructor directly.
    Register with a ``ToolRegistry`` before agents start.
    """

    requires_approval = False
    default_approval_mode = "direct"

    def __init__(
        self,
        name: str,
        description: str,
        target_agent_id: str | None = None,
        timeout: float = 90.0,
        question_description: str = _DEFAULT_QUESTION_DESC,
    ) -> None:
        self.name = name
        self.description = description
        self.input_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": question_description,
                }
            },
            "required": ["question"],
        }
        if not target_agent_id:
            self.input_schema["properties"]["agent"] = {
                "type": "string",
                "description": (
                    "Target agent id, e.g. GLOBL-ALL___-GA-NEWS1. "
                    "If not fixed in config, this field is required."
                ),
            }
            self.input_schema["required"].append("agent")
        self._target_agent_id = target_agent_id
        self._timeout = timeout

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        """Send AGENT_QUERY to target agent, await AGENT_QUERY_RESPONSE."""
        bus = context.event_bus
        if bus is None:
            return {"error": "EventBus not available in tool context."}

        target_agent_id = self._target_agent_id or str(arguments.get("agent", "")).strip()
        if not target_agent_id:
            return {
                "error": (
                    "No target agent provided. Configure 'target_agent_id' for this bridge tool "
                    "or pass argument 'agent'."
                )
            }

        if target_agent_id not in bus.registered_agents():
            _log.warning("AgentBridgeTool %r: target %r not registered", self.name, target_agent_id)
            return {
                "error": (
                    f"Target agent {target_agent_id!r} is not currently running. "
                    "It may still be starting up — retry in a moment, or proceed "
                    "without this information."
                )
            }

        correlation_id = str(uuid.uuid4())
        response_ready = asyncio.Event()
        result: dict[str, Any] = {}

        async def _on_response(msg: AgentMessage) -> None:
            if msg.correlation_id != correlation_id:
                return
            result["response"] = msg.payload.get("response", "")
            result["from_agent"] = msg.payload.get("agent_id", target_agent_id)
            response_ready.set()

        bus.subscribe(EventType.AGENT_QUERY_RESPONSE, _on_response)

        question = str(arguments.get("question", "Provide your current analysis.")).strip()
        _log.debug("AgentBridgeTool %r -> %r question=%r", self.name, target_agent_id, question[:80])

        await bus.publish(AgentMessage(
            event_type=EventType.AGENT_QUERY,
            source_agent_id=context.agent_id,
            target_agent_id=target_agent_id,
            payload={
                "question": question,
                "source": context.agent_id,
            },
            correlation_id=correlation_id,
        ))

        try:
            await asyncio.wait_for(response_ready.wait(), timeout=self._timeout)
            return {
                "response": result.get("response", ""),
                "from_agent": result.get("from_agent", target_agent_id),
            }
        except asyncio.TimeoutError:
            _log.warning(
                "AgentBridgeTool %r: no response from %r within %.0fs",
                self.name,
                target_agent_id,
                self._timeout,
            )
            return {
                "error": (
                    f"Agent {target_agent_id!r} did not respond within "
                    f"{self._timeout:.0f}s. It may be busy processing another cycle. "
                    "Consider retrying or proceeding without this information."
                )
            }
        finally:
            bus.unsubscribe(EventType.AGENT_QUERY_RESPONSE, _on_response)

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "AgentBridgeTool":
        """Create an ``AgentBridgeTool`` from a normalised config dict."""
        return cls(
            name=cfg["name"],
            description=cfg["description"],
            target_agent_id=cfg.get("target_agent_id"),
            timeout=float(cfg.get("timeout_seconds", 90.0)),
            question_description=cfg.get("question_description", _DEFAULT_QUESTION_DESC),
        )

    def __repr__(self) -> str:
        return (
            f"AgentBridgeTool(name={self.name!r}, "
            f"target={self._target_agent_id!r}, "
            f"timeout={self._timeout}s)"
        )


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return s or "target"


def _expand_bridge_tool_config(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one bridge tool config into one or many tool configs.

    Supported input forms:
    1. Classic single tool: name/description/target_agent_id
    2. Grouped multi-target: name + targets[]

    For targets[] entries:
    - required: target_agent_id (or agent_id)
    - recommended: tool_name (or name), description
    - optional: timeout_seconds, question_description, alias/label
    """
    targets = cfg.get("targets")
    if targets is None:
        if "target_agent_ids" in cfg:
            targets = cfg.get("target_agent_ids")
        else:
            return [dict(cfg)]

    if not isinstance(targets, list) or not targets:
        raise ValueError("bridge tool 'targets' must be a non-empty list")

    if "target_agent_id" in cfg:
        raise ValueError("bridge tool must use either 'target_agent_id' or 'targets', not both")

    base_name = str(cfg.get("name", "")).strip()
    base_desc = str(cfg.get("description", "")).strip()
    base_timeout = float(cfg.get("timeout_seconds", 90.0))
    base_question_desc = str(cfg.get("question_description", _DEFAULT_QUESTION_DESC))

    expanded: list[dict[str, Any]] = []
    for idx, target in enumerate(targets, start=1):
        target_cfg = dict(cfg)
        target_cfg.pop("targets", None)
        target_cfg.pop("target_agent_ids", None)

        if isinstance(target, str):
            target_id = target.strip()
            if not target_id:
                raise ValueError(f"bridge tool targets[{idx}] is empty")
            tool_name = f"{base_name}_{idx}" if base_name else f"bridge_target_{idx}"
            description = (
                f"{base_desc} (Target: {target_id})"
                if base_desc
                else f"Bridge query to {target_id}."
            )
            target_cfg.update({
                "name": tool_name,
                "description": description,
                "target_agent_id": target_id,
                "timeout_seconds": base_timeout,
                "question_description": base_question_desc,
            })
            expanded.append(target_cfg)
            continue

        if not isinstance(target, dict):
            raise ValueError(f"bridge tool targets[{idx}] must be object or string")

        target_id = str(target.get("target_agent_id") or target.get("agent_id") or "").strip()
        if not target_id:
            raise KeyError(f"bridge tool targets[{idx}] missing 'target_agent_id'")

        tool_name = str(target.get("tool_name") or target.get("name") or "").strip()
        if not tool_name:
            alias = str(target.get("alias") or target.get("label") or target_id).strip()
            if not base_name:
                raise KeyError(
                    f"bridge tool targets[{idx}] missing 'tool_name' and base config has no 'name'"
                )
            tool_name = f"{base_name}_{_slug(alias)}"

        description = str(target.get("description") or "").strip()
        if not description:
            description = (
                f"{base_desc} (Target: {target_id})"
                if base_desc
                else f"Bridge query to {target_id}."
            )

        target_cfg.update({
            "name": tool_name,
            "description": description,
            "target_agent_id": target_id,
            "timeout_seconds": float(target.get("timeout_seconds", base_timeout)),
            "question_description": str(
                target.get("question_description", base_question_desc)
            ),
        })
        expanded.append(target_cfg)

    return expanded


# ── Bootstrap helper ──────────────────────────────────────────────────────────

def register_bridge_tools_from_config(
    bridge_tool_configs: list[dict[str, Any]],
    registry: Any,
) -> int:
    """Create ``AgentBridgeTool`` instances from config dicts and register them."""
    count = 0
    for cfg in bridge_tool_configs:
        try:
            expanded_cfgs = _expand_bridge_tool_config(cfg)
        except Exception as exc:
            _log.error("Skipping bridge tool config group — invalid config: %s  cfg=%r", exc, cfg)
            continue

        for one_cfg in expanded_cfgs:
            try:
                tool = AgentBridgeTool.from_config(one_cfg)
                registry.register(tool)
                _log.info("Bridge tool registered: %r -> %s", tool.name, tool._target_agent_id)
                count += 1
            except KeyError as exc:
                _log.error(
                    "Skipping bridge tool — missing required config key %s in: %r",
                    exc,
                    one_cfg,
                )
            except Exception as exc:
                _log.error("Skipping bridge tool — unexpected error: %s  cfg=%r", exc, one_cfg)
    return count
