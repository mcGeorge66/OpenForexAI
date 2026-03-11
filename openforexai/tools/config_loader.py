"""Agent tool configuration loader.

Loads ``agent_tools.json5`` and resolves per-agent config using pattern matching.

Usage::

    config = AgentToolConfig.load(Path("config/RunTime/agent_tools.json5"))
    agent_cfg = config.for_agent("OANDA-EURUSD-AA-TRD1")
    # → {"allowed_tools": [...], "approval_modes": {...}, ...}
"""
from __future__ import annotations

import json5
import logging
from pathlib import Path

from openforexai.messaging.agent_id import AgentId

_log = logging.getLogger(__name__)


class AgentToolConfig:
    """Loaded and queryable agent tool configuration."""

    def __init__(self, entries: list[dict], bridge_tools: list[dict] | None = None) -> None:
        self._entries = entries  # ordered list of {pattern, ...} dicts
        self._bridge_tools = bridge_tools or []

    @classmethod
    def load(cls, path: Path) -> AgentToolConfig:
        """Load from a JSON5 file."""
        try:
            data = json5.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _log.warning("agent_tools.json5 not found at %s — using defaults", path)
            return cls([], [])
        except ValueError as exc:
            _log.error("Invalid JSON5 in agent_tools.json5: %s", exc)
            return cls([], [])
        return cls(data.get("agents", []), data.get("bridge_tools", []))

    def for_agent(self, agent_id: str) -> dict:
        """Return the config dict for *agent_id* (first matching pattern wins)."""
        aid = AgentId.try_parse(agent_id)
        for entry in self._entries:
            pattern = entry.get("pattern", "*")
            if pattern == "*":
                return entry
            if aid is not None and aid.matches(pattern):
                return entry
            # Fallback: exact string match
            if agent_id == pattern:
                return entry
        return {}

    def raw_bridge_tools(self) -> list[dict]:
        """Return bridge-tool configs from top-level ``bridge_tools``."""
        return list(self._bridge_tools)





