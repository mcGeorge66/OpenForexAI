"""Candle timestamps are stored in UTC, and only in UTC.

The candle tables keep ``timestamp`` as TEXT in both adapters, and both compare
it as text — ``ORDER BY timestamp`` and ``WHERE timestamp <= ?``. That only
matches real chronological order while every row carries the same offset. It
did not: MT5 delivers broker-local time and one path wrote UTC, which left 678
USDJPY and 478 EURUSD rows sitting in the wrong place, all in the 23:55–02:45
broker-time band.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from openforexai.utils.time_utils import candle_timestamp_key

BROKER_TZ = timezone(timedelta(hours=3))


def test_broker_time_becomes_utc() -> None:
    dt = datetime(2026, 7, 1, 12, 0, tzinfo=BROKER_TZ)
    assert candle_timestamp_key(dt) == "2026-07-01T09:00:00+00:00"


def test_utc_stays_utc() -> None:
    dt = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    assert candle_timestamp_key(dt) == "2026-07-01T09:00:00+00:00"


def test_naive_is_read_as_utc() -> None:
    """Matches candle_dicts_to_objects, which does the same."""
    dt = datetime(2026, 7, 1, 9, 0)
    assert candle_timestamp_key(dt) == "2026-07-01T09:00:00+00:00"


def test_same_instant_in_two_offsets_gives_one_key() -> None:
    """The reason the migration could collapse 26 duplicate rows safely."""
    broker = datetime(2026, 6, 22, 12, 35, tzinfo=BROKER_TZ)
    utc = datetime(2026, 6, 22, 9, 35, tzinfo=UTC)
    assert candle_timestamp_key(broker) == candle_timestamp_key(utc)


def test_text_order_equals_time_order() -> None:
    """The property the whole change exists for.

    Mixed offsets break it: 20:55+00:00 is chronologically LATER than
    20:55+03:00, but sorts earlier as text. Normalised, both orders agree.
    """
    mixed = [
        datetime(2026, 6, 5, 20, 55, tzinfo=UTC),        # 23:55 broker time
        datetime(2026, 6, 5, 20, 55, tzinfo=BROKER_TZ),  # 17:55 UTC — earlier
        datetime(2026, 6, 5, 23, 50, tzinfo=BROKER_TZ),  # 20:50 UTC
    ]
    raw = [dt.isoformat() for dt in mixed]
    assert sorted(raw) != sorted(raw, key=lambda s: datetime.fromisoformat(s).timestamp()), (
        "this test would prove nothing if the raw strings already sorted correctly"
    )

    keys = [candle_timestamp_key(dt) for dt in mixed]
    assert sorted(keys) == sorted(keys, key=lambda s: datetime.fromisoformat(s).timestamp())


@pytest.mark.parametrize("offset", [-8, -5, 0, 1, 2, 3, 9])
def test_any_offset_normalises_to_the_same_instant(offset: int) -> None:
    """A broker on EET moves to +02:00 in winter — the key must not care."""
    instant = datetime(2026, 11, 3, 14, 30, tzinfo=UTC)
    local = instant.astimezone(timezone(timedelta(hours=offset)))
    assert candle_timestamp_key(local) == "2026-11-03T14:30:00+00:00"
