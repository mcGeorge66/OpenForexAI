"""Tool: close_position — close an open position by ID.

Requires supervisor approval before execution.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext


class ClosePositionTool(BaseTool):
    name = "close_position"
    description = (
        "Close an open position by its broker position ID. "
        "Use get_open_positions to retrieve position IDs first. "
        "This tool requires supervisor approval before execution."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "position_id": {
                "type": "string",
                "description": "The broker-assigned position ID to close.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this position is being closed (logged).",
            },
        },
        "required": ["position_id"],
    }
    requires_approval = True
    default_approval_mode = "supervisor"

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        if context.broker is None:
            raise RuntimeError("Broker adapter not available in tool context")

        position_id = arguments["position_id"]
        result = await context.broker.close_position(position_id)

        return {
            "success": result.success,
            "position_id": position_id,
            "close_price": float(result.fill_price) if result.fill_price else None,
            "message": result.message,
        }
