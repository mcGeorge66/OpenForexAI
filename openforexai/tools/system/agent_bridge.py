"""AgentBridgeTool — config-driven inter-agent communication via AGENT_QUERY.

Concept
-------
Each AgentBridgeTool instance represents a named, LLM-callable tool that
internally routes the call to another running agent via the EventBus.

From the LLM's perspective it is identical to any other tool — it has a name,
a description, and accepts a ``question`` argument.  The LLM does not know (and
does not need to know) that a second agent is being invoked.

From the architecture's perspective the agents remain fully decoupled:
- The calling agent (e.g. AA) only sees a tool in its manifest.
- The target agent (e.g. GA news agent) only sees an ``AGENT_QUERY`` event.
- No code change in either agent is required.

Configuration (``config/agent_tools.json``)
-------------------------------------------
Add a top-level ``"bridge_tools"`` list::

    {
      "bridge_tools": [
        {
          "name":                "get_economic_news_analysis",
          "description":        "Returns current economic news analysis …",
          "target_agent_id":    "GLOBL_ALL..._GA_NEWS1",
          "timeout_seconds":    90,
          "question_description": "Optional specific question, e.g. …"
        }
      ],
      "agents": [ … ]
    }

Then list the tool name in the calling agent's ``allowed_tools``::

    { "pattern": "*_*_AA_*",
      "allowed_tools": ["get_candles", "get_economic_news_analysis", …] }

Bootstrap integration
---------------------
Call ``register_bridge_tools_from_config()`` once during startup, **before**
agents are created, so the tools are present in ``DEFAULT_REGISTRY`` when
agents initialise their ``ToolDispatcher``::

    from openforexai.tools.system.agent_bridge import register_bridge_tools_from_config
    from openforexai.tools import DEFAULT_REGISTRY
    from openforexai.tools.config_loader import AgentToolConfig

    tool_cfg = AgentToolConfig.load(Path("config/agent_tools.json"))
    register_bridge_tools_from_config(tool_cfg.raw_bridge_tools(), DEFAULT_REGISTRY)

Communication flow
------------------
1. AA-LLM decides to call ``get_economic_news_analysis(question="…")``
2. ``ToolDispatcher`` invokes ``AgentBridgeTool.execute()``
3. Tool subscribes to ``AGENT_QUERY_RESPONSE`` (filtered by correlation_id)
4. Tool publishes ``AGENT_QUERY`` with ``target_agent_id`` set
   → EventBus delivers directly to GA's queue (routing table bypassed)
5. GA's ``_run_message_loop`` picks up the event, runs ``_run_cycle()``
6. GA's LLM produces a response, publishes ``AGENT_QUERY_RESPONSE``
7. Bridge tool's handler fires, ``asyncio.Event`` is set
8. Tool returns the GA's response as a JSON-serialisable dict
9. AA-LLM continues its turn with the news analysis in its context
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.tools.base import BaseTool, ToolContext

_log = logging.getLogger(__name__)


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
        target_agent_id: str,
        timeout: float = 90.0,
        question_description: str = (
            "Your specific question or request. "
            "Be precise to get a focused answer."
        ),
    ) -> None:
        """
        Args:
            name:                 Tool name shown in the LLM manifest.
            description:          Tool description shown in the LLM manifest.
                                  This is what the LLM reads to decide when to call the tool.
            target_agent_id:      Full agent ID of the target agent, e.g.
                                  ``"GLOBL_ALL..._GA_NEWS1"``.
            timeout:              Seconds to wait for the target agent's response.
                                  Should be long enough for the target agent's LLM
                                  round-trip (typically 10–120 s).
            question_description: Description of the ``question`` input field,
                                  shown to the calling LLM.
        """
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
        self._target_agent_id = target_agent_id
        self._timeout = timeout

    # ── Tool execution ────────────────────────────────────────────────────────

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        """Send AGENT_QUERY to target agent, await AGENT_QUERY_RESPONSE.

        Uses the same ``asyncio.Event`` pattern as the supervisor approval flow:
        subscribe → publish → wait → unsubscribe.  No shared global state.
        """
        bus = context.event_bus
        if bus is None:
            return {"error": "EventBus not available in tool context."}

        # Guard: target agent must be registered (running)
        if self._target_agent_id not in bus.registered_agents():
            _log.warning(
                "AgentBridgeTool %r: target %r not registered",
                self.name, self._target_agent_id,
            )
            return {
                "error": (
                    f"Target agent {self._target_agent_id!r} is not currently running. "
                    "It may still be starting up — retry in a moment, or proceed "
                    "without this information."
                )
            }

        correlation_id = str(uuid.uuid4())
        response_ready = asyncio.Event()
        result: dict[str, Any] = {}

        # One-shot response handler — filtered by correlation_id
        async def _on_response(msg: AgentMessage) -> None:
            if msg.correlation_id != correlation_id:
                return  # not our response
            result["response"] = msg.payload.get("response", "")
            result["from_agent"] = msg.payload.get("agent_id", self._target_agent_id)
            response_ready.set()

        bus.subscribe(EventType.AGENT_QUERY_RESPONSE, _on_response)

        question = str(arguments.get("question", "Provide your current analysis.")).strip()
        _log.debug(
            "AgentBridgeTool %r → %r  question=%r",
            self.name, self._target_agent_id, question[:80],
        )

        await bus.publish(AgentMessage(
            event_type=EventType.AGENT_QUERY,
            source_agent_id=context.agent_id,
            target_agent_id=self._target_agent_id,   # direct delivery, bypasses routing table
            payload={
                "question": question,
                "source": context.agent_id,
            },
            correlation_id=correlation_id,
        ))

        try:
            await asyncio.wait_for(response_ready.wait(), timeout=self._timeout)
            return {
                "response":   result.get("response", ""),
                "from_agent": result.get("from_agent", self._target_agent_id),
            }
        except asyncio.TimeoutError:
            _log.warning(
                "AgentBridgeTool %r: no response from %r within %.0fs",
                self.name, self._target_agent_id, self._timeout,
            )
            return {
                "error": (
                    f"Agent {self._target_agent_id!r} did not respond within "
                    f"{self._timeout:.0f}s. It may be busy processing another cycle. "
                    "Consider retrying or proceeding without this information."
                )
            }
        finally:
            bus.unsubscribe(EventType.AGENT_QUERY_RESPONSE, _on_response)

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "AgentBridgeTool":
        """Create an ``AgentBridgeTool`` from a config dict.

        Required keys: ``name``, ``description``, ``target_agent_id``.
        Optional keys: ``timeout_seconds`` (default 90), ``question_description``.

        Raises:
            KeyError:   if a required key is missing.
            ValueError: if a value has an invalid type.
        """
        return cls(
            name=cfg["name"],
            description=cfg["description"],
            target_agent_id=cfg["target_agent_id"],
            timeout=float(cfg.get("timeout_seconds", 90.0)),
            question_description=cfg.get(
                "question_description",
                "Your specific question or request. Be precise to get a focused answer.",
            ),
        )

    def __repr__(self) -> str:
        return (
            f"AgentBridgeTool(name={self.name!r}, "
            f"target={self._target_agent_id!r}, "
            f"timeout={self._timeout}s)"
        )


# ── Bootstrap helper ──────────────────────────────────────────────────────────

def register_bridge_tools_from_config(
    bridge_tool_configs: list[dict[str, Any]],
    registry: Any,  # ToolRegistry — avoided import to prevent circular deps
) -> int:
    """Create ``AgentBridgeTool`` instances from config dicts and register them.

    Call once during bootstrap, **before** agents are started, so the tools
    are present in the registry when agents initialise their ``ToolDispatcher``.

    Args:
        bridge_tool_configs:  List of bridge-tool config dicts (the value of
                              ``"bridge_tools"`` in ``agent_tools.json``).
        registry:             ``ToolRegistry`` instance (typically
                              ``openforexai.tools.DEFAULT_REGISTRY``).

    Returns:
        Number of tools successfully registered.

    Example::

        from openforexai.tools.system.agent_bridge import register_bridge_tools_from_config
        from openforexai.tools import DEFAULT_REGISTRY
        import json

        raw = json.loads(Path("config/agent_tools.json").read_text())
        n = register_bridge_tools_from_config(raw.get("bridge_tools", []), DEFAULT_REGISTRY)
        print(f"Registered {n} bridge tool(s)")
    """
    count = 0
    for cfg in bridge_tool_configs:
        try:
            tool = AgentBridgeTool.from_config(cfg)
            registry.register(tool)
            _log.info("Bridge tool registered: %r → %s", tool.name, tool._target_agent_id)
            count += 1
        except KeyError as exc:
            _log.error(
                "Skipping bridge tool — missing required config key %s in: %r", exc, cfg
            )
        except Exception as exc:
            _log.error("Skipping bridge tool — unexpected error: %s  cfg=%r", exc, cfg)
    return count
