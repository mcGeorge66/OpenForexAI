"""Ein geschlossenes Tor darf keinen Alarm ausloesen.

Gemessen an 450 USDJPY-Trades bricht das FOMAK-Tor rund drei Viertel aller
Analystenzyklen ab. Das ist der Zweck. Meldet sich der Abbruch nicht, haelt der
Gesundheitswaechter jeden dieser Zyklen fuer einen haengenden Agenten — bei
einer Kerze alle fuenf Minuten heisst das Dauerfeuer auf Telegram, und die
eine echte Stoerung geht darin unter.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from openforexai.models.monitoring import MonitoringEvent, MonitoringEventType
from openforexai.monitoring.agent_health import STALE_GRACE_SECONDS, compute_agent_stale
from openforexai.monitoring.bus import MonitoringBus


CFG = {"event_triggers": ["m5_candle"]}


def _bus() -> MonitoringBus:
    return MonitoringBus(detail_level="INFO")


def _delivery(agent_id: str, when: datetime) -> MonitoringEvent:
    return MonitoringEvent(
        timestamp=when, source_module="eventbus",
        event_type=MonitoringEventType.EVENT_BUS_MESSAGE,
        payload={"event": "m5_candle", "target": agent_id},
    )


def _skipped(agent_id: str, when: datetime, reason: str) -> MonitoringEvent:
    return MonitoringEvent(
        timestamp=when, source_module=f"agent:{agent_id}",
        event_type=MonitoringEventType.AGENT_TRIGGER_SKIPPED,
        payload={"agent_id": agent_id, "reason": reason},
    )


def test_an_unanswered_trigger_is_a_stall() -> None:
    """Die Gegenprobe: ohne Meldung muss der Waechter anschlagen, sonst
    prueft der Test darunter nichts."""
    bus = _bus()
    delivered = datetime(2026, 9, 17, 3, 45, tzinfo=UTC)
    bus._track_agent_activity(_delivery("AA", delivered))
    stale, reason = compute_agent_stale(
        CFG, delivered + timedelta(seconds=STALE_GRACE_SECONDS + 5), None,
        bus.agent_pending_triggers("AA"))
    assert stale and "m5_candle" in (reason or "")


def test_the_gate_closing_clears_the_trigger() -> None:
    bus = _bus()
    delivered = datetime(2026, 9, 17, 3, 45, tzinfo=UTC)
    bus._track_agent_activity(_delivery("AA", delivered))
    bus._track_agent_activity(_skipped(
        "AA", delivered + timedelta(seconds=2),
        "assembly_cancel: FOMAK 1D121O ausserhalb der Handelsgruppe"))
    stale, reason = compute_agent_stale(
        CFG, delivered + timedelta(seconds=STALE_GRACE_SECONDS + 5), None,
        bus.agent_pending_triggers("AA"))
    assert not stale, f"Tor zu, aber als Stillstand gewertet: {reason}"


def test_the_cancel_path_really_reports_it() -> None:
    """Der Test oben prueft den Waechter. Dieser prueft, dass die Abbruchstelle
    die Meldung ueberhaupt absetzt — sonst passen beide Haelften nicht."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[2] / "openforexai" / "agents" / "agent.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    treffer = []
    for node in ast.walk(tree):
        # if decision_snapshot.get("cancel"): ...
        if not isinstance(node, ast.If):
            continue
        quelle = ast.unparse(node.test)
        if "cancel" not in quelle or "decision_snapshot" not in quelle:
            continue
        koerper = ast.unparse(node)
        treffer.append(koerper)

    assert treffer, "Abbruchstelle nicht gefunden — Pruefung laeuft ins Leere"
    for koerper in treffer:
        assert "_emit_agent_trigger_skipped" in koerper, (
            "Der Abbruch meldet sich nicht — jeder geschlossene Zyklus loest "
            "wieder einen Stale-Alarm aus")
