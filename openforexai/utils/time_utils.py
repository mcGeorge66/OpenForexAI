from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def detect_session(dt: datetime | None = None) -> str:
    """Return the dominant forex market session for a given UTC datetime.

    Sessions (approximate UTC hours):
      - sydney:   21:00 – 06:00
      - tokyo:    00:00 – 09:00
      - london:   07:00 – 16:00
      - new_york: 12:00 – 21:00
      - overlap:  07:00 – 09:00 (Tokyo/London) | 12:00 – 16:00 (London/NY)
    """
    if dt is None:
        dt = utcnow()

    hour = dt.hour

    london_open = 7 <= hour < 16
    ny_open = 12 <= hour < 21
    tokyo_open = 0 <= hour < 9
    sydney_open = hour >= 21 or hour < 6

    if london_open and ny_open:
        return "overlap"
    if london_open and tokyo_open:
        return "overlap"
    if london_open:
        return "london"
    if ny_open:
        return "new_york"
    if tokyo_open:
        return "tokyo"
    if sydney_open:
        return "sydney"
    return "closed"


def is_market_open(dt: datetime | None = None) -> bool:
    """Return True if at least one major forex session is active."""
    return detect_session(dt) != "closed"


def candle_timestamp_key(dt: datetime) -> str:
    """The one storage format for a candle timestamp: UTC, ISO-8601.

    Candle tables keep ``timestamp`` as TEXT and both adapters compare it as
    text — ``ORDER BY timestamp`` and ``WHERE timestamp <= ?``. That only
    matches the real chronological order while every row carries the same UTC
    offset. It did not: MT5 delivers broker-local time (+03:00 in summer) and
    one code path wrote UTC, so 678 USDJPY and 478 EURUSD rows sat in the wrong
    place, all of them in the 23:55–02:45 broker-time band. Every ATR, EMA and
    swing level computed over a window crossing that band was reading a
    shuffled series.

    UTC everywhere keeps text order and time order identical for good — a fixed
    broker offset would not, because a broker on EET moves to +02:00 in winter
    and both offsets would be legitimate again.

    Display is unaffected: the UI formats from the instant via ``ui_utc``.

    A naive datetime is read as UTC, matching ``candle_dicts_to_objects``.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).isoformat()
    return dt.astimezone(UTC).isoformat()

