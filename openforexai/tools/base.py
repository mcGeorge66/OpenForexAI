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
(``agent_tools.json5``) before calling ``execute()``.  Approval modes:

- ``"direct"``           — always execute without extra checks (default for most tools)
- ``"supervisor"``       — route through the SupervisorAgent (trading/close tools)
- ``"human"``            — block until a human explicitly approves via Management API

The approval mode is configured per-tool per-agent in ``agent_tools.json5``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Runtime context passed to every tool call."""
    agent_id: str
    broker_name: str | None = None
    pair: str | None = None
    data_container: Any = None          # openforexai.data.container.DataContainer
    repository: Any = None              # AbstractRepository
    broker: Any = None                  # AbstractBroker (the pair's broker adapter)
    monitoring_bus: Any = None          # AbstractMonitoringBus
    event_bus: Any = None               # EventBus
    extra: dict[str, Any] = field(default_factory=dict)


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

