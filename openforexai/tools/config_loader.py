"""Agent tool configuration loader.

Loads ``agent_tools.json`` and resolves per-agent config using pattern matching.

Usage::

    config = AgentToolConfig.load(Path("config/agent_tools.json"))
    agent_cfg = config.for_agent("OANDA_EURUSD_AA_TRD1")
    # → {"allowed_tools": [...], "approval_modes": {...}, ...}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from openforexai.messaging.agent_id import AgentId

_log = logging.getLogger(__name__)


class AgentToolConfig:
    """Loaded and queryable agent tool configuration."""

    def __init__(self, entries: list[dict]) -> None:
        self._entries = entries  # ordered list of {pattern, ...} dicts

    @classmethod
    def load(cls, path: Path) -> AgentToolConfig:
        """Load from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _log.warning("agent_tools.json not found at %s — using defaults", path)
            return cls([])
        except json.JSONDecodeError as exc:
            _log.error("Invalid JSON in agent_tools.json: %s", exc)
            return cls([])
        return cls(data.get("agents", []))

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
