"""Tool: raise_alarm — emit a structured alarm to the MonitoringBus.

Agents use this tool when they detect anomalies, critical conditions, or
situations that require human attention.  Alarms are routed to the
MonitoringBus and can be forwarded to notification channels.
"""
from __future__ import annotations

from typing import Any

from openforexai.tools.base import BaseTool, ToolContext

_VALID_SEVERITIES = {"info", "warning", "error", "critical"}


class RaiseAlarmTool(BaseTool):
    name = "raise_alarm"
    description = (
        "Emit a structured alarm to the monitoring system. "
        "Use for: unusual market conditions, API errors, risk limit warnings, "
        "data integrity issues, or any situation needing human awareness. "
        "Severity levels: info | warning | error | critical."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "description": "Alarm severity: info | warning | error | critical",
                "enum": ["info", "warning", "error", "critical"],
            },
            "title": {
                "type": "string",
                "description": "Short alarm title (max 100 chars).",
                "maxLength": 100,
            },
            "message": {
                "type": "string",
                "description": "Detailed alarm message explaining what was detected.",
            },
            "context": {
                "type": "object",
                "description": "Optional additional key-value data attached to the alarm.",
                "additionalProperties": True,
            },
        },
        "required": ["severity", "title", "message"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        import logging
        from datetime import datetime, timezone

        severity = arguments.get("severity", "warning").lower()
        if severity not in _VALID_SEVERITIES:
            severity = "warning"

        title = str(arguments.get("title", "Agent Alarm"))[:100]
        message = str(arguments.get("message", ""))
        extra_context = arguments.get("context", {}) or {}

        alarm_payload = {
            "severity": severity,
            "title": title,
            "message": message,
            "agent_id": context.agent_id,
            "broker_name": context.broker_name,
            "pair": context.pair,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra_context,
        }

        # Log to Python logging (always)
        log = logging.getLogger("openforexai.alarm")
        log_fn = getattr(log, severity if severity != "critical" else "critical", log.warning)
        log_fn("[ALARM][%s] %s — %s", context.agent_id, title, message)

        # Emit to MonitoringBus
        if context.monitoring_bus is not None:
            try:
                from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
                context.monitoring_bus.emit(MonitoringEvent(
                    timestamp=datetime.now(timezone.utc),
                    source_module=f"agent:{context.agent_id}",
                    event_type=MonitoringEventType.AGENT_ALARM,
                    broker_name=context.broker_name,
                    pair=context.pair,
                    payload=alarm_payload,
                ))
            except Exception:
                pass  # monitoring must never block the agent

        return {
            "alarm_raised": True,
            "severity": severity,
            "title": title,
        }
