"""How long a position was held belongs in the event, not in every consumer.

Notification templates cannot calculate, and an agent should not have to
re-derive it from two timestamps that arrive in different timezones —
opened_at comes from the broker with its own offset, requested_at in UTC.
"""
from __future__ import annotations

from openforexai.repository_service import _held_for


def test_derives_hours_and_minutes_across_timezones():
    """Real shape from the order book: UTC request, broker-offset fill/close."""
    out = _held_for({
        "requested_at": "2026-09-14T17:06:39.739046+00:00",
        "opened_at": "2026-09-14T20:06:39+03:00",
        "closed_at": "2026-09-14T22:27:56+03:00",
    })
    assert out == {"held_minutes": 141, "held_for": "2h 21min"}


def test_short_trade_reads_without_a_zero_hour():
    out = _held_for({
        "opened_at": "2026-09-14T19:26:36+03:00",
        "closed_at": "2026-09-14T19:43:22+03:00",
    })
    assert out == {"held_minutes": 16, "held_for": "16min"}


def test_falls_back_to_requested_at_when_the_fill_time_is_missing():
    """Two of 987 closed entries never recorded opened_at."""
    out = _held_for({
        "requested_at": "2026-09-14T17:00:00+00:00",
        "opened_at": None,
        "closed_at": "2026-09-14T18:30:00+00:00",
    })
    assert out["held_minutes"] == 90


def test_missing_or_broken_timestamps_yield_nothing_rather_than_raising():
    """A notification must never break its own delivery over a bad field."""
    assert _held_for({}) == {}
    assert _held_for({"opened_at": "irgendwas", "closed_at": "2026-09-14T18:00:00+00:00"}) == {}
    assert _held_for({"opened_at": "2026-09-14T18:00:00+00:00", "closed_at": ""}) == {}


def test_naive_timestamps_are_refused_rather_than_guessed():
    """Without an offset the difference would be wrong by the broker offset."""
    assert _held_for({"opened_at": "2026-09-14T18:00:00", "closed_at": "2026-09-14T19:00:00"}) == {}


def test_close_before_open_is_not_reported_as_negative():
    assert _held_for({
        "opened_at": "2026-09-14T19:00:00+00:00",
        "closed_at": "2026-09-14T18:00:00+00:00",
    }) == {}
