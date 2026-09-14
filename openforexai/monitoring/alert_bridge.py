"""Put auto-pinned monitoring errors onto the EventBus.

The MonitoringBus already decides which events matter enough to survive
ring-buffer eviction (``_AUTO_PIN_TYPES``): failed cycles, failed LLM turns,
failed EC runs, failed tool calls, broker errors. That is the same threshold as
"worth telling a human about" — but monitoring is in-memory and only helps
someone who happens to be looking at the dashboard.

This bridge republishes those onto the EventBus, where they become durable in
the event log and can drive the configurable notification rules. Deliberately a
bridge rather than a bus publish at each emit site: there are a dozen such
sites, a new one is easy to forget, and anything added to ``_AUTO_PIN_TYPES``
later is covered here without touching code elsewhere.

One event type for all of them. The payloads differ per source (``agent_id``
vs ``ec_id`` vs ``broker_name``), so separate bus types would mean a new enum
member, a new schema entry and a new notification rule for every kind of
failure. Instead the kind travels in ``alert_type`` and the original payload is
merged in, so a single rule can catch everything while still filtering on the
kind and using the source-specific fields as placeholders.
"""
from __future__ import annotations

import asyncio
from typing import Any

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.monitoring.bus import _AUTO_PIN_TYPES
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

ALERT_BRIDGE_ID = "SYSTM-ALL___-GA-ALERT"

# Already published on the bus by whoever raises it, with a richer payload than
# the monitoring copy. Bridging it too would notify twice for one failure.
_ALREADY_ON_THE_BUS = frozenset({MonitoringEventType.SYSTEM_ERROR})

# What is worth telling a human about. Starts from the monitoring bus's own
# judgement of what must survive eviction — so a kind added there is covered
# here without touching this module — plus the one non-error that matters:
# a broker coming back. Deliberately a separate set rather than an addition to
# _AUTO_PIN_TYPES, which means "protect from eviction" and should stay errors
# only; a successful reconnect does not belong on an error pinboard.
_ALERT_TYPES = frozenset(_AUTO_PIN_TYPES) | {MonitoringEventType.BROKER_CONNECTED}

# Tried in order; the first present field becomes {message}. Every source names
# its failure differently, and a rule should not have to know which.
_MESSAGE_FIELDS = ("error", "message", "detail", "reason")


def alert_payload(event: Any) -> dict[str, Any]:
    """Build the bus payload for one monitoring event."""
    original = event.payload if isinstance(getattr(event, "payload", None), dict) else {}
    message = ""
    for field in _MESSAGE_FIELDS:
        value = original.get(field)
        if isinstance(value, str) and value.strip():
            message = value.strip()
            break
    payload: dict[str, Any] = {
        "alert_type": str(event.event_type),
        "source": str(getattr(event, "source_module", "") or ""),
        "message": message,
        "broker": getattr(event, "broker_name", None),
        "pair": getattr(event, "pair", None),
    }
    # Original fields last so a source-specific "source" or "message" wins over
    # the envelope — the more specific value is the more useful one.
    payload.update(original)
    payload["alert_type"] = str(event.event_type)
    return payload


def should_bridge(event: Any) -> bool:
    event_type = str(getattr(event, "event_type", ""))
    if event_type not in _ALERT_TYPES:
        return False
    return event_type not in _ALREADY_ON_THE_BUS


async def alert_bridge_loop(monitoring_bus: Any, bus: Any) -> None:
    """Forward auto-pinned monitoring errors to the EventBus until cancelled."""
    queue = monitoring_bus.subscribe()
    _log.info("Alert bridge started", member_id=ALERT_BRIDGE_ID)
    try:
        while True:
            event = await queue.get()
            if not should_bridge(event):
                continue
            try:
                await bus.publish(AgentMessage(
                    event_type=EventType.SYSTEM_ALERT,
                    source_agent_id=ALERT_BRIDGE_ID,
                    payload=alert_payload(event),
                ))
            except Exception as exc:
                # Reporting a failure must never create one.
                _log.error("Alert bridge could not publish", error=str(exc))
    except asyncio.CancelledError:
        raise
    finally:
        try:
            monitoring_bus.unsubscribe(queue)
        except Exception:
            pass
