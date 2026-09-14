"""Staleness must follow an agent's real triggers, not a wall clock.

The examiner agent (EA-EXAM) runs only on position_closed and is idle for hours
by design; a fixed "idle for 15 minutes" rule flagged it constantly, which
trains everyone to ignore the badge. These tests pin both directions: silent
when the agent had nothing to do, immediate when a trigger went unanswered.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from openforexai.management import api


class _FakeMonitoringBus:
    def __init__(self, last_active=None, pending=None):
        self._last_active = last_active
        self._pending = pending or {}

    def agent_last_active(self, agent_id: str):
        return self._last_active

    def agent_pending_triggers(self, agent_id: str):
        return dict(self._pending)


@pytest.fixture
def now():
    return datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _restore_bus():
    original = api._monitoring_bus
    yield
    api._monitoring_bus = original


def _set_bus(**kwargs):
    api._monitoring_bus = _FakeMonitoringBus(**kwargs)


def test_event_driven_agent_idle_without_triggers_is_not_stale(now):
    """The reported false alarm: examiner idle for hours, nothing to react to."""
    _set_bus(last_active=now - timedelta(hours=6), pending={})
    cfg = {"event_triggers": ["position_closed"], "timer": {"enabled": False}}

    stale, reason = api._compute_agent_stale(cfg, "OXS_T-ALL___-EA-EXAM", now)

    assert stale is False
    assert reason is None


def test_unanswered_trigger_is_stale_immediately(now):
    """One missed position_closed is already money — no waiting for a second."""
    _set_bus(
        last_active=now - timedelta(hours=6),
        pending={"position_closed": (1, now - timedelta(seconds=120))},
    )
    cfg = {"event_triggers": ["position_closed"], "timer": {"enabled": False}}

    stale, reason = api._compute_agent_stale(cfg, "OXS_T-ALL___-EA-EXAM", now)

    assert stale is True
    assert "position_closed" in reason


def test_trigger_within_grace_is_not_yet_stale(now):
    """A cycle that is just starting must not be reported as a stall."""
    _set_bus(
        last_active=now - timedelta(hours=6),
        pending={"position_closed": (1, now - timedelta(seconds=5))},
    )
    cfg = {"event_triggers": ["position_closed"], "timer": {"enabled": False}}

    stale, _ = api._compute_agent_stale(cfg, "OXS_T-ALL___-EA-EXAM", now)

    assert stale is False


def test_deliberate_skips_clear_the_backlog_so_no_stale(now):
    """AnyCandle/llm-busy/session skips are logged by the agent, which clears
    the pending entry — so a healthy divider-skipping agent shows nothing here."""
    _set_bus(last_active=now - timedelta(minutes=10), pending={})
    cfg = {"event_triggers": ["m5_candle_trigger"], "AnyCandle": 3, "timer": {"enabled": False}}

    stale, _ = api._compute_agent_stale(cfg, "OXS_T-EURUSD-AA-PTJ", now)

    assert stale is False


def test_candle_agent_stale_on_first_unprocessed_trigger(now):
    """Not processed and not skipped means the agent never saw it — flag at once,
    without waiting for a second or third candle."""
    _set_bus(
        last_active=now - timedelta(minutes=20),
        pending={"m5_candle_trigger": (1, now - timedelta(seconds=300))},
    )
    cfg = {"event_triggers": ["m5_candle_trigger"], "AnyCandle": 3, "timer": {"enabled": False}}

    stale, reason = api._compute_agent_stale(cfg, "OXS_T-EURUSD-AA-PTJ", now)

    assert stale is True
    assert "m5_candle_trigger" in reason


def test_responses_to_own_requests_are_not_triggers(now):
    """Only configured triggers count — llm/repo replies are deliveries too."""
    _set_bus(
        last_active=now - timedelta(hours=3),
        pending={
            "llm_response": (12, now - timedelta(seconds=600)),
            "repo_response": (40, now - timedelta(seconds=600)),
        },
    )
    cfg = {"event_triggers": ["position_closed"], "timer": {"enabled": False}}

    stale, _ = api._compute_agent_stale(cfg, "OXS_T-ALL___-EA-EXAM", now)

    assert stale is False


def test_manual_triggers_never_mark_an_agent_stale(now):
    """agent_query/prompt_updated are fired by a human, not the system."""
    _set_bus(
        last_active=now - timedelta(hours=3),
        pending={"agent_query": (1, now - timedelta(seconds=600))},
    )
    cfg = {"event_triggers": ["agent_query", "prompt_updated"], "timer": {"enabled": False}}

    stale, _ = api._compute_agent_stale(cfg, "OXS_T-ALL___-EA-EXAM", now)

    assert stale is False


def test_timer_agent_stale_when_interval_elapsed_without_a_cycle(now):
    _set_bus(last_active=now - timedelta(seconds=400), pending={})
    cfg = {"event_triggers": [], "timer": {"enabled": True, "interval_seconds": 300}}

    stale, reason = api._compute_agent_stale(cfg, "SOME-TIMER-AGENT", now)

    assert stale is True
    assert "300" in reason


def test_timer_agent_within_interval_is_not_stale(now):
    _set_bus(last_active=now - timedelta(seconds=120), pending={})
    cfg = {"event_triggers": [], "timer": {"enabled": True, "interval_seconds": 300}}

    stale, _ = api._compute_agent_stale(cfg, "SOME-TIMER-AGENT", now)

    assert stale is False


def test_agent_that_never_ran_is_not_reported_as_stale(now):
    """Right after startup there is no evidence of a stall yet."""
    _set_bus(last_active=None, pending={})
    cfg = {"event_triggers": [], "timer": {"enabled": True, "interval_seconds": 300}}

    stale, _ = api._compute_agent_stale(cfg, "SOME-TIMER-AGENT", now)

    assert stale is False
