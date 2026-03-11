"""Demo: minimal tool template for OpenForexAI.

Copy this file, rename the class and file, and adjust:
1. name
2. description
3. input_schema
4. execute()
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class DemoMinimalTool(BaseTool):
    # Must be globally unique in ToolRegistry.
    name = "demo_minimal"

    # Keep this concise and action-oriented. The LLM reads this text directly.
    description = "Return a simple greeting and basic runtime context."

    # JSON schema for tool arguments.
    # This is shown to the LLM and to UI ToolExecutor.
    input_schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Short message to echo back.",
            },
        },
        "required": ["message"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        """Tool execution entrypoint.

        Input sources:
        - arguments: user/LLM payload validated by schema shape.
        - context: runtime state injected by dispatcher/API.

        Output destination:
        - return value is serialized and sent back as the tool result.
        """
        msg = str(arguments.get("message", "")).strip()
        if not msg:
            raise ValueError("message is required")

        return {
            "ok": True,
            "echo": msg,
            "agent_id": context.agent_id,
            "broker_name": context.broker_name,
            "pair": context.pair,
        }

