"""ToolRegistry — plug-and-play tool registration.

Analogous to ``IndicatorRegistry``: add a tool in one line and it becomes
available to all agents that have it in their ``agent_tools.json`` config.

Usage::

    from openforexai.tools.registry import DEFAULT_REGISTRY

    # Register a custom tool
    DEFAULT_REGISTRY.register(MyCustomTool())

    # Get tool spec for LLM
    specs = DEFAULT_REGISTRY.specs_for(["get_candles", "calculate_indicator"])
"""
from __future__ import annotations

import logging

from openforexai.tools.base import BaseTool

_log = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all tool plugins.

    Maps tool names → BaseTool instances.  Supports iteration and filtered
    spec-list generation for the LLM provider.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._ordered: list[BaseTool] = []

    def register(self, tool: BaseTool) -> None:
        """Register *tool* by its ``name``.  Replaces any existing registration."""
        if tool.name in self._tools:
            _log.debug("ToolRegistry: replacing existing tool %r", tool.name)
            self._ordered = [t for t in self._ordered if t.name != tool.name]
        self._tools[tool.name] = tool
        self._ordered.append(tool)
        _log.debug("ToolRegistry: registered %r", tool.name)

    def unregister(self, name: str) -> None:
        """Remove the tool registered under *name*."""
        tool = self._tools.pop(name, None)
        if tool is not None:
            self._ordered = [t for t in self._ordered if t.name != name]

    def get(self, name: str) -> BaseTool | None:
        """Return the tool for *name*, or ``None`` if not registered."""
        return self._tools.get(name)

    def all_tools(self) -> list[BaseTool]:
        """Return all registered tools in insertion order."""
        return list(self._ordered)

    def all_names(self) -> list[str]:
        """Return canonical names of all registered tools."""
        return [t.name for t in self._ordered]

    def specs_for(self, names: list[str]) -> list[dict]:
        """Return ToolSpec dicts for the given *names* (LLM tool manifest).

        Unknown names are silently skipped.
        """
        specs = []
        for name in names:
            tool = self._tools.get(name)
            if tool is not None:
                specs.append(tool.to_spec())
            else:
                _log.warning("ToolRegistry.specs_for: unknown tool %r — skipped", name)
        return specs

    def specs_all(self) -> list[dict]:
        """Return ToolSpec dicts for ALL registered tools."""
        return [t.to_spec() for t in self._ordered]


# ── Default registry — populated by tools package __init__ ────────────────────
DEFAULT_REGISTRY = ToolRegistry()
