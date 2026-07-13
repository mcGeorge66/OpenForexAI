from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class AssessmentMemoryTool(BaseTool):
    name = "assessment_memory"
    description = (
        "Get or set a persisted assessment-memory message for a target agent. "
        "Use this when one agent needs to store a compact message that another agent can load later."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agentid": {"type": "string", "description": "Target agent id."},
            "mode": {"type": "string", "enum": ["get", "set"], "description": "Operation to perform."},
            "message": {"type": "string", "description": "Message to persist when mode is set."},
        },
        "required": ["agentid", "mode"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        agentid = str(arguments.get("agentid", "")).strip()
        mode = str(arguments.get("mode", "")).strip().lower()

        if not agentid:
            return {"error": "Argument 'agentid' is required."}

        if mode == "get":
            message = await repo_request(context, "get_assessment_memory", {"agent": agentid})
            return {"agentid": agentid, "mode": mode, "message": message, "exists": message is not None}

        if mode != "set":
            return {"error": f"Unsupported mode: {mode!r}."}

        message = arguments.get("message")
        if not isinstance(message, str):
            return {"error": "Argument 'message' is required for mode='set'."}

        await repo_request(context, "set_assessment_memory", {"agent": agentid, "message": message})
        return {"agentid": agentid, "mode": mode, "message": message, "length": len(message)}
