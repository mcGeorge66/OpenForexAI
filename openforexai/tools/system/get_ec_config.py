"""Tool: get_ec_config — fetch an EventComposer's live, resolved configuration.

Reuses the exact same resolution ConfigService performs for a real EC on startup
(EC_CONFIG_REQUESTED -> EC_CONFIG_RESPONSE): script, config_json, tool_config,
event_triggers, and the resolved snapshot_profile (if configured). Always
reflects the CURRENT configuration.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, bus_request


class GetEcConfigTool(BaseTool):
    name = "get_ec_config"
    description = (
        "Fetch an EventComposer's LIVE configuration: its script, config_json, tool_config, "
        "event_triggers, and resolved snapshot_profile (if any). This reflects the current "
        "configuration. Use this to inspect e.g. a trailing-stop or risk-guard EC that may "
        "have acted on a trade, or to tell the user exactly which EC/field to edit."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ec_id": {"type": "string", "description": "EventComposer id, e.g. 'OXS_T-EURUSD-EC-TRSLF'."},
        },
        "required": ["ec_id"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        ec_id = str(arguments.get("ec_id", "")).strip()
        if not ec_id:
            return {"error": "Argument 'ec_id' is required."}

        from openforexai.config.config_service import CONFIG_SERVICE_ID
        from openforexai.models.messaging import EventType

        try:
            return await bus_request(
                context, EventType.EC_CONFIG_REQUESTED, CONFIG_SERVICE_ID,
                {"ec_id": ec_id}, timeout=10.0,
            )
        except TimeoutError:
            return {
                "error": f"No response for ec_id {ec_id!r} — check that it exists and is enabled.",
            }
