from __future__ import annotations

from pathlib import Path

from openforexai.tools.config_loader import AgentToolConfig


def test_agent_tool_config_loads_only_bridge_tools() -> None:
    cfg_path = Path.cwd() / "config" / "RunTime" / "agent_tools.json5"
    loaded = AgentToolConfig.load(cfg_path)

    assert loaded.raw_bridge_tools() == [
        {
            "name": "ask_ga_market_outlook",
            "description": "Ask a global analysis agent for an additional market outlook and return its answer.",
            "timeout_seconds": 90,
            "question_description": "Specific question for the target agent, e.g. macro drivers for the next hours.",
        }
    ]
