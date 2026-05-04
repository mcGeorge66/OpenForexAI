"""Bridge-tool configuration loader.

Loads ``agent_tools.json5`` and exposes only top-level ``bridge_tools``.
Per-agent tool assignment is configured explicitly in each agent's
``tool_config`` inside the system config.
"""
from __future__ import annotations

import logging
from pathlib import Path

import json5

_log = logging.getLogger(__name__)


class AgentToolConfig:
    """Loaded bridge-tool configuration."""

    def __init__(self, bridge_tools: list[dict] | None = None) -> None:
        self._bridge_tools = bridge_tools or []

    @classmethod
    def load(cls, path: Path) -> AgentToolConfig:
        """Load from a JSON5 file."""
        try:
            data = json5.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _log.warning("agent_tools.json5 not found at %s — using defaults", path)
            return cls([])
        except ValueError as exc:
            _log.error("Invalid JSON5 in agent_tools.json5: %s", exc)
            return cls([])
        return cls(data.get("bridge_tools", []))

    def raw_bridge_tools(self) -> list[dict]:
        """Return bridge-tool configs from top-level ``bridge_tools``."""
        return list(self._bridge_tools)





