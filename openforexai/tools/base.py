"""BaseTool ABC — interface every tool plugin must implement.

A tool is a callable that agents can invoke via the LLM tool-use API.
Each concrete tool:

1. Declares its ``name``, ``description``, and ``input_schema`` (ToolSpec).
2. Implements ``execute(arguments, context)`` which runs the actual logic.
3. Optionally marks itself ``requires_approval = True`` so the ToolDispatcher
   routes it through an approval gate before executing.

Context object
--------------
``ToolContext`` is passed to every tool execution.  It carries references to
shared system components so tools can access live data without importing globals.

Approval flow
-------------
When ``requires_approval`` is True the dispatcher checks the per-agent config
(``config/system.json5`` → ``agents.<id>.tool_config``) before calling ``execute()``.
Approval modes:

- ``"direct"``           — always execute without extra checks (default for most tools)
- ``"supervisor"``       — route through the SupervisorAgent (trading/close tools)
- ``"human"``            — block until a human explicitly approves via Management API

The approval mode is configured per-tool per-agent in ``config/system.json5``.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)
_tool_defaults_cache: dict[str, Any] | None = None

def _load_tool_defaults() -> dict[str, Any]:
    """Load config/llm_tool_config.json5 once and cache it."""
    global _tool_defaults_cache
    if _tool_defaults_cache is not None:
        return _tool_defaults_cache
    path = Path(__file__).parents[2] / "config" / "llm_tool_config.json5"
    if not path.exists():
        _tool_defaults_cache = {}
        return _tool_defaults_cache
    try:
        import json5
        data = json5.loads(path.read_text(encoding="utf-8"))
        _tool_defaults_cache = data if isinstance(data, dict) else {}
    except Exception as exc:
        _log.warning("Could not load llm_tool_config.json5: %s", exc)
        _tool_defaults_cache = {}
    return _tool_defaults_cache


def get_tool_default(tool_name: str, param: str, fallback: Any = None) -> Any:
    """Return the configured default for a tool parameter, or fallback if not set."""
    defaults = _load_tool_defaults()
    tool_cfg = defaults.get(tool_name)
    if isinstance(tool_cfg, dict) and param in tool_cfg:
        return tool_cfg[param]
    return fallback


@dataclass
class ToolContext:
    """Runtime context passed to every tool call.

    All inter-module communication goes through ``event_bus``.
    Direct references to broker, data_container, and repository have been
    removed — use ``bus_request()`` to communicate with those modules.
    """
    agent_id: str
    broker_name: str | None = None   # short_name for routing target resolution
    pair: str | None = None          # current pair for routing target resolution
    monitoring_bus: Any = None       # AbstractMonitoringBus (one-way observability)
    event_bus: Any = None            # EventBus — the only inter-module channel
    extra: dict[str, Any] = field(default_factory=dict)


def candle_dicts_to_objects(raw: list) -> list:
    """Convert candle dicts from bus responses to Candle objects."""
    from datetime import datetime, timezone
    from openforexai.models.market import Candle
    result = []
    for cd in raw:
        try:
            if not isinstance(cd, dict):
                result.append(cd)
                continue
            ts = cd.get("timestamp", "")
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                cd = {**cd, "timestamp": dt}
            result.append(Candle(**cd))
        except Exception:
            pass
    return result


async def bus_request(
    context: ToolContext,
    event_type,
    target_id: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send a request event and wait for the correlated response.

    This is the standard pattern for all inter-module tool calls.
    The caller publishes an event with a unique correlation_id and
    registers a Future that is resolved when the response arrives.

    Args:
        context:    Tool context (provides agent_id and event_bus).
        event_type: EventType to publish (e.g. EventType.ORDER_REQUEST).
        target_id:  Target member ID for direct delivery (bypasses routing).
        payload:    Request payload dict.
        timeout:    Seconds to wait for the response (default 30).

    Returns:
        The response payload dict.

    Raises:
        asyncio.TimeoutError: If no response arrives within *timeout* seconds.
        RuntimeError: If event_bus is not set in context.
    """
    bus = context.event_bus
    if bus is None:
        raise RuntimeError("bus_request: event_bus not set in ToolContext")

    from openforexai.models.messaging import AgentMessage

    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()

    # Request carries NO correlation_id — prevents dispatch loop from resolving
    # the future when it processes the request itself. The response echoes
    # str(request.id) as correlation_id, which is registered below.
    msg = AgentMessage(
        event_type=event_type,
        source_agent_id=context.agent_id,
        target_agent_id=target_id,
        payload=payload,
        # correlation_id intentionally NOT set
    )
    future_key = str(msg.id)
    bus.register_response_future(future_key, future)
    await bus.publish(msg)

    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        raise
    finally:
        bus.cancel_response_future(future_key)


async def repo_request(
    context: ToolContext,
    operation: str,
    args: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> Any:
    """Send a REPO_REQUEST to the RepositoryService and return the result.

    Args:
        context:   Tool context.
        operation: AbstractRepository method name (e.g. "get_sub_prompt").
        args:      Keyword arguments to pass to the method.
        timeout:   Seconds to wait (default 15).

    Returns:
        The method's return value.

    Raises:
        RuntimeError: If the repository service returns an error.
        asyncio.TimeoutError: If no response arrives in time.
    """
    from openforexai.models.messaging import EventType
    from openforexai.repository_service import REPO_SERVICE_ID

    response = await bus_request(
        context=context,
        event_type=EventType.REPO_REQUEST,
        target_id=REPO_SERVICE_ID,
        payload={"operation": operation, "args": args or {}},
        timeout=timeout,
    )
    if response.get("error"):
        raise RuntimeError(f"Repository operation '{operation}' failed: {response['error']}")
    return response.get("result")


class BaseTool(ABC):
    """Base class for all tool plugins.

    Subclass this, set the class-level attributes, and implement ``execute()``.
    Register an instance with a ``ToolRegistry`` to make the tool available to agents.

    Example::

        class GetCandlesTool(BaseTool):
            name = "get_candles"
            description = "Retrieve OHLCV candle data for a currency pair."
            input_schema = {
                "type": "object",
                "properties": {
                    "timeframe": {"type": "string", "description": "M5 | M15 | H1 | H4 | D1"},
                    "count":     {"type": "integer", "description": "Number of candles (1-500)"},
                },
                "required": ["timeframe"],
            }

            async def execute(self, arguments: dict, context: ToolContext) -> Any:
                tf = arguments.get("timeframe", "H1")
                count = min(int(arguments.get("count", 50)), 500)
                candles = context.data_container.get_candles(
                    context.broker_name, context.pair, tf
                )
                return [c.model_dump() for c in candles[-count:]]
    """

    #: Canonical tool name — must be unique within a registry.
    name: str

    #: Short, LLM-readable description (shown in the tool manifest).
    description: str

    #: JSON-schema for the tool's arguments (Anthropic ``input_schema`` format).
    input_schema: dict[str, Any]

    #: When True, the dispatcher checks per-agent approval config before executing.
    requires_approval: bool = False

    #: Default approval mode if not overridden in agent config.
    #: "direct" | "supervisor" | "human"
    default_approval_mode: str = "direct"

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """Execute the tool and return a JSON-serialisable result.

        Raise any exception to signal an error; the dispatcher wraps it as an
        ``is_error=True`` ToolResult automatically.
        """
        ...

    def to_spec(self) -> dict[str, Any]:
        """Return the canonical ToolSpec dict for the LLM provider."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

