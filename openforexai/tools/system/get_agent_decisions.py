"""Tool: get_agent_decisions — recent decision history for an agent (not just the latest).

get_last_decision only ever returns "whatever is latest right now" — useless for
investigating a past trade, since by the time someone asks, the agent has usually
moved on to many newer decisions. This returns a window of recent decisions so the
caller can find the one that actually matches a specific past timestamp.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class GetAgentDecisionsTool(BaseTool):
    name = "get_agent_decisions"
    description = (
        "Fetch an agent's recent stored decisions (newest first) — each with the raw analysis "
        "text, parsed decision JSON, snapshot_profile/decision_prompt_profile used, and "
        "timestamp. Use this (not get_last_decision) to find the specific decision cycle around "
        "a particular past time, e.g. whichever decision preceded a trade's close_requested_at."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent id."},
            "pair": {"type": "string", "description": "Optional currency pair filter."},
            "limit": {
                "type": "integer",
                "description": "Max decisions to return (1-50). Default 20.",
                "minimum": 1, "maximum": 50,
            },
        },
        "required": ["agent_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        agent_id = str(arguments.get("agent_id", "")).strip()
        if not agent_id:
            return {"error": "Argument 'agent_id' is required."}
        pair = str(arguments.get("pair", "")).strip() or None
        limit = min(int(arguments.get("limit", 20)), 50)
        records = await repo_request(
            context, "get_analysis_records", {"agent_id": agent_id, "pair": pair, "limit": limit},
        ) or []
        return {"agent_id": agent_id, "decisions": records}
