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

Beyond that floor of errors, *which* monitoring kinds get forwarded is read
from the rules themselves (``only_if.alert_type``). Of the 60 monitoring kinds
only a handful are errors; alerting on one of the rest — a full agent queue,
say — is therefore a rule in the designer rather than a change here.

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


def requested_alert_types(notification_service: Any) -> set[str]:
    """Monitoring kinds the configured rules ask for, beyond the error floor.

    A rule on ``system_alert`` names the kind it wants in
    ``only_if.alert_type``. Reading it here means the bridge no longer holds a
    hard-coded list: forwarding a new kind is a rule in the Telegram designer,
    not a code change — the same shape as the routing entries derived from
    these rules.

    Only literal values can be enumerated. A ``contains`` or ``regex``
    condition could match kinds nobody can list in advance, so such a rule
    sees only what is already forwarded; that is logged rather than left
    silent, because a rule that can never fire looks like a broken channel.
    """
    requested: set[str] = set()
    rules = getattr(notification_service, "rules", None)
    if not isinstance(rules, dict):
        return requested
    for name, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        if notification_service.rule_event(name, rule) != EventType.SYSTEM_ALERT.value:
            continue
        condition = (rule.get("only_if") or {}).get("alert_type")
        if isinstance(condition, str) and condition.strip():
            requested.add(condition.strip())
        elif condition is not None:
            _log.warning(
                "Alert rule cannot be resolved to a monitoring kind — it only "
                "sees kinds already forwarded",
                rule=name, condition=str(condition),
            )
    return requested


def should_bridge(event: Any, extra_types: frozenset[str] | set[str] = frozenset()) -> bool:
    event_type = str(getattr(event, "event_type", ""))
    if event_type not in _ALERT_TYPES and event_type not in extra_types:
        return False
    return event_type not in _ALREADY_ON_THE_BUS


async def alert_bridge_loop(
    monitoring_bus: Any,
    bus: Any,
    notification_service: Any = None,
) -> None:
    """Forward alert-worthy monitoring events to the EventBus until cancelled.

    The rules are read per event rather than cached, so a rule added in the
    designer takes effect immediately — the project rule is that configuration
    works without a restart.
    """
    queue = monitoring_bus.subscribe()
    _log.info("Alert bridge started", member_id=ALERT_BRIDGE_ID)
    try:
        while True:
            event = await queue.get()
            extra = requested_alert_types(notification_service) if notification_service else set()
            if not should_bridge(event, extra):
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
