"""Demo: tool template showing context usage + outbound event/monitoring.

This script demonstrates:
- Reading data from ToolContext (broker_name, pair, data_container, extra["llm"])
- Emitting monitoring events
- Publishing a message to EventBus
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.tools.base import BaseTool, ToolContext


class DemoContextEventTool(BaseTool):
    name = "demo_context_event"
    description = (
        "Inspect context, optionally read latest candles, emit a monitoring event, "
        "and optionally publish an EventBus message."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "emit_bus_message": {
                "type": "boolean",
                "description": "Publish a demo event to EventBus.",
            },
            "timeframe": {
                "type": "string",
                "description": "Timeframe for optional candle preview.",
                "enum": ["M5", "M15", "M30", "H1", "H4", "D1"],
            },
            "count": {
                "type": "integer",
                "description": "How many candles to fetch (1-20).",
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        emit_bus_message = bool(arguments.get("emit_bus_message", False))
        timeframe = str(arguments.get("timeframe", "M5")).upper()
        count = max(1, min(int(arguments.get("count", 5)), 20))

        # Data source #1: runtime context injected by the system.
        llm_name = context.extra.get("llm_name")
        has_llm = context.extra.get("llm") is not None

        candle_preview: list[dict[str, Any]] = []
        # Data source #2: data_container for market data.
        if context.data_container and context.broker_name and context.pair:
            candles = await context.data_container.get_candles(
                context.broker_name,
                context.pair,
                timeframe,
            )
            for c in candles[-count:]:
                candle_preview.append(
                    {
                        "timestamp": c.timestamp.isoformat(),
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                    }
                )

        # Output sink #1: monitoring bus (fire-and-forget).
        if context.monitoring_bus is not None:
            context.monitoring_bus.emit(
                MonitoringEvent(
                    timestamp=datetime.now(UTC),
                    source_module=f"tool:{self.name}",
                    event_type=MonitoringEventType.SYSTEM_INFO,
                    broker_name=context.broker_name,
                    pair=context.pair,
                    payload={
                        "tool": self.name,
                        "agent_id": context.agent_id,
                        "emit_bus_message": emit_bus_message,
                        "llm_name": llm_name,
                    },
                )
            )

        # Output sink #2: EventBus (optional domain event publication).
        if emit_bus_message and context.event_bus is not None:
            await context.event_bus.publish(
                AgentMessage(
                    event_type=EventType.ROUTING_RELOAD_REQUESTED,
                    source_agent_id=context.agent_id,
                    payload={
                        "reason": "demo_context_event_tool",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            )

        # Output sink #3: returned JSON result to caller (UI/API/agent).
        return {
            "ok": True,
            "context": {
                "agent_id": context.agent_id,
                "broker_name": context.broker_name,
                "pair": context.pair,
                "llm_name": llm_name,
                "has_llm_instance": has_llm,
            },
            "candle_preview": candle_preview,
            "bus_message_emitted": emit_bus_message and context.event_bus is not None,
        }

