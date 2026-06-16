from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


class ManageSubPromptTool(BaseTool):
    name = "manage_sub_prompt"
    description = (
        "Read, replace, append, or delete a database-backed sub-prompt for a target agent. "
        "Use this to adjust another agent's runtime behavior extension."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Target agent id whose sub-prompt should be managed."},
            "command": {
                "type": "string",
                "enum": ["read", "replace", "append", "delete"],
                "description": "Operation to perform on the target agent sub-prompt.",
            },
            "prompt": {"type": "string", "description": "Prompt text used by replace or append."},
        },
        "required": ["agent", "command"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        agent = str(arguments.get("agent", "")).strip()
        command = str(arguments.get("command", "")).strip().lower()
        prompt = arguments.get("prompt")

        if not agent:
            return {"error": "Argument 'agent' is required."}

        if command == "read":
            current = await repo_request(context, "get_sub_prompt", {"agent": agent})
            return {"agent": agent, "command": command, "prompt": current, "exists": current is not None}

        if command == "delete":
            await repo_request(context, "delete_sub_prompt", {"agent": agent})
            return {"agent": agent, "command": command, "deleted": True}

        if command not in {"replace", "append"}:
            return {"error": f"Unsupported command: {command!r}."}

        if not isinstance(prompt, str):
            return {"error": "Argument 'prompt' is required for replace and append."}

        if command == "append":
            current = await repo_request(context, "get_sub_prompt", {"agent": agent})
            prompt = f"{current}{prompt}" if current else prompt

        await repo_request(context, "set_sub_prompt", {"agent": agent, "prompt": prompt})
        return {"agent": agent, "command": command, "prompt": prompt, "length": len(prompt)}
