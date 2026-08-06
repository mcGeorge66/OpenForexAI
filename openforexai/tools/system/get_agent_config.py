"""Tool: get_agent_config — fetch an agent's live, resolved configuration.

Reuses the exact same resolution ConfigService performs when a real agent starts
up (AGENT_CONFIG_REQUESTED -> AGENT_CONFIG_RESPONSE): system_prompt merged with
the DB sub-prompt, snapshot_profile/decision_prompt_profile resolved to their
full contents, sanitized tool_config. Always reflects the CURRENT config, which
may differ from what was active for a specific past decision.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, bus_request


class GetAgentConfigTool(BaseTool):
    name = "get_agent_config"
    description = (
        "Fetch an AA/BA/GA agent's LIVE configuration: its resolved system prompt (static "
        "config + DB sub-prompt merged), snapshot_profile/decision_prompt_profile names and "
        "their full resolved contents, tool_config, and event triggers. This reflects the "
        "current configuration — it may have changed since a specific past decision was made. "
        "Use this to tell the user exactly which agent/field to edit for a requested change."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent id, e.g. 'OXS_T-EURUSD-AA-PTJ'."},
        },
        "required": ["agent_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        agent_id = str(arguments.get("agent_id", "")).strip()
        if not agent_id:
            return {"error": "Argument 'agent_id' is required."}

        from openforexai.config.config_service import CONFIG_SERVICE_ID
        from openforexai.models.messaging import EventType

        try:
            return await bus_request(
                context, EventType.AGENT_CONFIG_REQUESTED, CONFIG_SERVICE_ID,
                {"agent_id": agent_id}, timeout=10.0,
            )
        except TimeoutError:
            return {
                "error": f"No response for agent_id {agent_id!r} — check that it exists and is enabled.",
            }
