"""Tool: send_notification — push a message to the operator's notification channel.

Available to agents (via allowed_tools) and to EC scripts (via
``await tools.call("send_notification", ...)``). Both go through the same
NotificationService, so deduplication, the hourly cap and the dry-run switch
apply no matter who sends.

Access is deliberately opt-in per agent/EC through ``allowed_tools``. Where an
agent should not be free to choose urgency, pin ``severity`` via the agent's
``tool_config.forced_arguments`` — the same mechanism that pins memory tables.
"""
from __future__ import annotations

from typing import Any

from openforexai.models.messaging import EventType
from openforexai.services.notification_service import NOTIFICATION_SERVICE_ID
from openforexai.tools.base import BaseTool, ToolContext, bus_request

_VALID_SEVERITIES = ("info", "warning", "critical")


class SendNotificationTool(BaseTool):
    name = "send_notification"
    description = (
        "Send a short message to the operator's notification channel (Telegram). "
        "Use for situations a human should know about promptly — not for routine "
        "status updates. Repeated identical messages are suppressed automatically, "
        "so sending the same alert again is harmless but pointless. "
        "Severity: info (muted) | warning | critical."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "description": "info (silent) | warning | critical",
                "enum": list(_VALID_SEVERITIES),
            },
            "title": {
                "type": "string",
                "description": "Short headline, max 100 chars.",
                "maxLength": 100,
            },
            "message": {
                "type": "string",
                "description": "The message body. Keep it brief — long texts are truncated.",
            },
            "dedup_key": {
                "type": "string",
                "description": (
                    "Optional grouping key. Messages sharing a key are suppressed while "
                    "one is still recent. Defaults to severity+title."
                ),
            },
        },
        "required": ["severity", "title", "message"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        severity = str(arguments.get("severity", "info")).lower()
        if severity not in _VALID_SEVERITIES:
            severity = "info"

        payload = {
            "severity": severity,
            "title": str(arguments.get("title", ""))[:100],
            "message": str(arguments.get("message", "")),
            "dedup_key": arguments.get("dedup_key"),
            "sender": context.agent_id,
        }
        response = await bus_request(
            context,
            EventType.NOTIFY_REQUEST,
            target_id=NOTIFICATION_SERVICE_ID,
            payload=payload,
            timeout=30.0,
        )
        if response.get("error"):
            raise RuntimeError(f"Notification failed: {response['error']}")
        return response.get("result", {"sent": False, "reason": "no_result"})
