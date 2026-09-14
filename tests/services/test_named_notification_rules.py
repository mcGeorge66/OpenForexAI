"""Rules are keyed by a free name, not by the event they react to.

Keyed by event type there could only ever be one rule per event: no separate
message for a rejected order and a filled one, and no way to forward two
monitor filters, since both arrive as system_alert. Existing configurations
that use the event type as the key keep working — the key is then the event.
"""
from __future__ import annotations

import pytest

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.services.notification_service import NotificationService


def _service(rules) -> NotificationService:
    svc = NotificationService(enabled=False, rules=rules)
    svc.sent: list[dict] = []                      # type: ignore[attr-defined]

    async def _capture(args):
        svc.sent.append(args)                      # type: ignore[attr-defined]
        return {"sent": True}

    svc.notify = _capture                          # type: ignore[assignment]
    return svc


# ── Resolving which event a rule listens to ──────────────────────────────────

def test_a_rule_without_an_event_field_uses_its_key():
    """Backwards compatibility: that is how every existing config is written."""
    assert NotificationService.rule_event("order_result", {"title": "x"}) == "order_result"


def test_an_event_field_wins_over_the_key():
    assert NotificationService.rule_event("meine_regel", {"event": "system_alert"}) == "system_alert"


def test_a_blank_event_field_falls_back_to_the_key():
    assert NotificationService.rule_event("order_result", {"event": "   "}) == "order_result"


# ── Several rules on one event ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_rules_on_the_same_event_both_fire():
    svc = _service({
        "order_abgelehnt": {"event": "order_result", "only_if": {"success": False}, "title": "abgelehnt"},
        "order_gefuellt":  {"event": "order_result", "only_if": {"success": True},  "title": "gefuellt"},
    })
    await svc._handle_routed_event(AgentMessage(
        event_type=EventType.ORDER_RESULT, source_agent_id="x", payload={"success": False}))
    assert [s["title"] for s in svc.sent] == ["abgelehnt"]


@pytest.mark.asyncio
async def test_both_matching_rules_send_separately():
    svc = _service({
        "a": {"event": "order_result", "title": "A"},
        "b": {"event": "order_result", "title": "B"},
    })
    await svc._handle_routed_event(AgentMessage(
        event_type=EventType.ORDER_RESULT, source_agent_id="x", payload={}))
    assert sorted(s["title"] for s in svc.sent) == ["A", "B"]


@pytest.mark.asyncio
async def test_rules_on_one_event_get_distinct_dedup_keys():
    """Shared keys would let one rule silence the other for the dedup window."""
    svc = _service({
        "a": {"event": "order_result", "title": "A"},
        "b": {"event": "order_result", "title": "B"},
    })
    await svc._handle_routed_event(AgentMessage(
        event_type=EventType.ORDER_RESULT, source_agent_id="x", payload={}))
    keys = {s["dedup_key"] for s in svc.sent}
    assert len(keys) == 2, keys


@pytest.mark.asyncio
async def test_a_broken_rule_does_not_silence_the_others():
    svc = _service({
        "kaputt": {"event": "order_result", "only_if": {"x": {"unbekannter_operator": 1}}, "title": "K"},
        "heil":   {"event": "order_result", "title": "H"},
    })
    await svc._handle_routed_event(AgentMessage(
        event_type=EventType.ORDER_RESULT, source_agent_id="x", payload={}))
    assert [s["title"] for s in svc.sent] == ["H"]


# ── Derived routing ──────────────────────────────────────────────────────────

def test_routing_is_derived_from_events_not_keys():
    """Two rules on one event must not produce two identical routing entries."""
    svc = _service({
        "a": {"event": "order_result"},
        "b": {"event": "order_result"},
        "c": {"event": "system_alert"},
        "risk_breach": {},
    })
    assert svc.rule_event_types() == {"order_result", "system_alert", "risk_breach"}
