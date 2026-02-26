from __future__ import annotations

from datetime import datetime, time, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
