"""Every deliberate pass must be logged, including "outside my session window".

Staleness is derived from unanswered triggers: a trigger the agent never logged
a decision about counts as missed. The session branch was the one skip path that
returned silently, so an agent behaving exactly as configured — idle because its
trading session is closed — was reported as stalled (USDJPY AA-PTJ, 2026-09-14).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from openforexai.agents.agent import Agent
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.monitoring import MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus


def _agent(monitoring_bus: MonitoringBus, *, session_allowed: bool) -> Agent:
    agent = Agent.__new__(Agent)
    agent.agent_id = "OXS_T-USDJPY-AA-PTJ"
    agent._running = True
    agent._inbox = asyncio.Queue()
    agent._run_lock = asyncio.Lock()
    agent._monitoring_bus = monitoring_bus
    agent._tool_dispatcher = None
    agent._config = {}
    agent._event_triggers = {EventType.M5_CANDLE_TRIGGER.value}
    agent._any_candle_divider = 1
    agent._m5_candle_event_count = 0
    agent._session_filter = [{"session": "new_york"}]
    agent._logger = _NullLogger()
    agent._is_session_allowed = lambda ts: session_allowed          # type: ignore[method-assign]
    agent._publish_m5_trigger_counter = _anoop                       # type: ignore[method-assign]
    agent._run_cycle = _anoop                                        # type: ignore[method-assign]
    return agent


async def _anoop(*args, **kwargs):
    return None


class _NullLogger:
    def __getattr__(self, _name):
        return lambda *a, **k: None


async def _drain(agent: Agent) -> None:
    """Run the message loop until the inbox is empty, then stop it."""
    task = asyncio.create_task(agent._run_message_loop())
    for _ in range(200):
        await asyncio.sleep(0)
        if agent._inbox.empty():
            break
    agent._running = False
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _delivery(agent_id: str, *, minutes_ago: int = 0):
    from openforexai.models.monitoring import MonitoringEvent
    return MonitoringEvent(
        timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        source_module="eventbus",
        event_type=EventType.M5_CANDLE_TRIGGER.value,
        payload={"event": EventType.M5_CANDLE_TRIGGER.value, "target": agent_id},
    )


def _trigger() -> AgentMessage:
    return AgentMessage(
        event_type=EventType.M5_CANDLE_TRIGGER,
        source_agent_id="OXS_T-USDJPY-AD-ADPT",
        target_agent_id="OXS_T-USDJPY-AA-PTJ",
        payload={"candle": {"timestamp": datetime.now(UTC).isoformat()}},
    )


async def test_trigger_outside_the_session_window_is_logged_as_skipped():
    bus = MonitoringBus(detail_level="DEBUG")
    agent = _agent(bus, session_allowed=False)
    await agent._inbox.put(_trigger())

    await _drain(agent)

    skips = [e for e in bus.recent_events(limit=20)
             if e.event_type == MonitoringEventType.AGENT_TRIGGER_SKIPPED]
    assert len(skips) == 1, "the session branch returned without logging the skip"
    assert skips[0].payload["reason"] == "session_filter"
    assert skips[0].payload["agent_id"] == agent.agent_id


async def test_the_skip_clears_a_trigger_the_bus_already_recorded():
    """End to end: delivery recorded, session closed, agent reports not stale.

    The delivery is backdated past the grace period — without the skip being
    logged this is exactly the state that produced the false alarm.
    """
    from openforexai.monitoring.agent_health import compute_agent_stale

    bus = MonitoringBus(detail_level="INFO")
    agent = _agent(bus, session_allowed=False)
    bus.emit(_delivery(agent.agent_id, minutes_ago=5))
    await agent._inbox.put(_trigger())

    await _drain(agent)

    stale, reason = compute_agent_stale(
        {"event_triggers": [EventType.M5_CANDLE_TRIGGER.value], "timer": {"enabled": False}},
        datetime.now(UTC),
        bus.agent_last_active(agent.agent_id),
        bus.agent_pending_triggers(agent.agent_id),
    )
    assert stale is False, reason


async def test_a_trigger_inside_the_session_still_runs_a_cycle():
    """Regression guard: the new emit must not swallow the normal path."""
    bus = MonitoringBus(detail_level="INFO")
    agent = _agent(bus, session_allowed=True)
    ran: list[str] = []

    async def _record_cycle(*_a, **kwargs):
        ran.append(kwargs.get("trigger", ""))

    agent._run_cycle = _record_cycle  # type: ignore[method-assign]
    await agent._inbox.put(_trigger())

    await _drain(agent)

    assert ran == [EventType.M5_CANDLE_TRIGGER.value]


def test_skipped_events_are_not_debug_only():
    """The emit helper must not be gated on the monitoring detail level —
    that gate is what made every skip invisible at INFO, so nothing ever
    cleared a pending trigger and normal behaviour looked like a stall."""
    bus = MonitoringBus(detail_level="INFO")
    agent = _agent(bus, session_allowed=False)
    bus.emit(_delivery(agent.agent_id, minutes_ago=5))
    assert bus.agent_pending_triggers(agent.agent_id) != {}

    agent._emit_agent_trigger_skipped(
        event_val=EventType.M5_CANDLE_TRIGGER.value,
        source="OXS_T-USDJPY-AD-ADPT",
        reason="session_filter",
        backlog_remaining=0,
        trigger_age_ms=None,
    )

    assert bus.agent_pending_triggers(agent.agent_id) == {}
    # Counted, but kept out of the INFO event log.
    assert not [e for e in bus.recent_events(limit=10)
                if e.event_type == MonitoringEventType.AGENT_TRIGGER_SKIPPED]


async def test_every_m5_trigger_emits_a_counter_event():
    """The counter the Monitor view filters on was never emitted: the payload
    referenced `cycle_pair`, a local from a different method, so every call
    raised NameError into a bare `except Exception: pass`."""
    bus = MonitoringBus(detail_level="DEBUG")
    agent = _agent(bus, session_allowed=False)
    agent._config = {"pair": "USDJPY"}
    del agent._publish_m5_trigger_counter          # use the real implementation
    await agent._inbox.put(_trigger())

    await _drain(agent)

    counters = [e for e in bus.recent_events(limit=50)
                if str(e.event_type) == EventType.M5_TRIGGER_COUNTER.value]
    assert len(counters) == 1, "no m5_trigger_counter reached the monitoring bus"
    p = counters[0].payload
    assert p["pair"] == "USDJPY"
    assert p["agent_id"] == agent.agent_id
    assert p["session"] is False
    assert p["run"] is False
