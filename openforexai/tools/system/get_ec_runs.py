"""Tool: get_ec_runs — recent run history for one EventComposer."""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class GetEcRunsTool(BaseTool):
    name = "get_ec_runs"
    description = (
        "Fetch recent run history for one EventComposer: trigger, input/output JSON, tool "
        "calls made (with arguments and results), success/error, and latency, newest first. "
        "Use this to see whether/when a specific EC (e.g. a trailing-stop or risk-guard) acted "
        "around the time of a specific trade."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ec_id": {"type": "string", "description": "EventComposer id."},
            "limit": {
                "type": "integer",
                "description": "Max runs to return (1-50). Default 10.",
                "minimum": 1, "maximum": 50,
            },
        },
        "required": ["ec_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        ec_id = str(arguments.get("ec_id", "")).strip()
        if not ec_id:
            return {"error": "Argument 'ec_id' is required."}
        limit = min(int(arguments.get("limit", 10)), 50)
        runs = await repo_request(context, "get_ec_runs", {"ec_id": ec_id, "limit": limit}) or []
        return {"ec_id": ec_id, "runs": runs}
