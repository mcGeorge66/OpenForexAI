from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class GetLastDecisionTool(BaseTool):
    name = "get_last_decision"
    description = (
        "Retrieve the last stored analysis decision for a given agent from the database. "
        "Returns the most recent decision record including bias, confidence, order_start_signal, "
        "entry_quality, and the full output payload."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agentid": {"type": "string", "description": "Agent ID whose last decision should be retrieved."},
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        agent_id = str(arguments.get("agentid", "")).strip() or (context.agent_id or "")
        if not agent_id:
            return {"error": "Argument 'agentid' is required."}

        records = await repo_request(
            context, "get_analysis_records", {"agent_id": agent_id, "limit": 1}
        )
        if not records:
            return {"agent_id": agent_id, "found": False, "decision": None}

        return {"agent_id": agent_id, "found": True, "decision": records[0]}
