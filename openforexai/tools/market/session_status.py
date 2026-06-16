"""Tool: get_session_status — Forex session state, liquidity, and trade recommendation."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import holidays as hols

from openforexai.tools.base import BaseTool, ToolContext

_SESSIONS = [
    {"name": "sydney",   "tz": "Australia/Sydney", "open": 8,  "close": 17, "country": "AU"},
    {"name": "tokyo",    "tz": "Asia/Tokyo",        "open": 8,  "close": 17, "country": "JP"},
    {"name": "london",   "tz": "Europe/London",     "open": 8,  "close": 17, "country": "GB"},
    {"name": "new_york", "tz": "America/New_York",  "open": 8,  "close": 17, "country": "US"},
]

# Primary sessions per currency — used for pair-specific relevance scoring.
# USD is present in ~88% of all trades; we list new_york as primary but it is
# always implicitly liquid whenever any major session is open.
_CURRENCY_SESSIONS: dict[str, list[str]] = {
    "AUD": ["sydney", "tokyo"],
    "NZD": ["sydney", "tokyo"],
    "JPY": ["tokyo"],
    "SGD": ["tokyo"],
    "HKD": ["tokyo"],
    "EUR": ["london"],
    "GBP": ["london"],
    "CHF": ["london"],
    "USD": ["new_york"],
    "CAD": ["new_york"],
}

# Session relevance rank used for pair_liquidity scoring (higher = more liquid).
_SESSION_RANK = {"sydney": 1, "tokyo": 2, "london": 4, "new_york": 4}


def _pair_primary_sessions(pair: str) -> list[str]:
    """Return deduplicated primary session list for a currency pair (e.g. 'EURUSD')."""
    pair = pair.upper().replace("/", "").replace("_", "").replace("-", "")
    if len(pair) < 6:
        return []
    base, quote = pair[:3], pair[3:6]
    seen: set[str] = set()
    result: list[str] = []
    for ccy in (base, quote):
        for sess in _CURRENCY_SESSIONS.get(ccy, []):
            if sess not in seen:
                seen.add(sess)
                result.append(sess)
    return result


def _pair_context(pair: str, sessions: dict[str, Any], active_names: list[str]) -> dict[str, Any]:
    """Build pair-specific session context block."""
    primary = _pair_primary_sessions(pair)
    if not primary:
        return {}

    active_set    = set(active_names)
    primary_set   = set(primary)
    active_primary = [s for s in primary if s in active_set]

    # Current relevance
    if primary_set <= active_set:
        current_relevance = "optimal"       # all primary sessions open
    elif active_primary:
        current_relevance = "partial"       # some primary sessions open
    else:
        current_relevance = "off_hours"     # no primary session open

    # Pair-specific liquidity: sum rank of active primary sessions
    rank_sum = sum(_SESSION_RANK.get(s, 0) for s in active_primary)
    if rank_sum == 0:
        pair_liquidity = "very_low"
    elif rank_sum <= 1:
        pair_liquidity = "low"
    elif rank_sum <= 2:
        pair_liquidity = "medium"
    elif rank_sum <= 4:
        pair_liquidity = "high"
    else:
        pair_liquidity = "very_high"

    # Override to very_high for the premier pair liquidity window
    if {"london", "new_york"} <= active_set and {"EUR", "GBP", "CHF", "USD", "CAD"} & {pair[:3], pair[3:6]}:
        pair_liquidity = "very_high"

    return {
        "pair":              pair.upper()[:6],
        "primary_sessions":  primary,
        "active_primary":    active_primary,
        "current_relevance": current_relevance,
        "pair_liquidity":    pair_liquidity,
    }


def get_session_status(utc_dt: datetime, pair: str | None = None) -> dict[str, Any]:
    """Return complete Forex session state for the given UTC timestamp.

    Args:
        utc_dt: UTC datetime (timezone-aware or naive, assumed UTC).
        pair:   Optional currency pair (e.g. 'EURUSD') for pair-specific context.
    """
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=UTC)

    sessions: dict[str, Any] = {}
    for sess in _SESSIONS:
        name     = sess["name"]
        tz       = ZoneInfo(sess["tz"])
        open_m   = sess["open"]  * 60
        close_m  = sess["close"] * 60
        country  = sess["country"]

        local_dt     = utc_dt.astimezone(tz)
        local_date   = local_dt.date()
        current_m    = local_dt.hour * 60 + local_dt.minute
        is_holiday   = local_date in hols.country_holidays(country, years=local_date.year)

        is_weekend = local_dt.weekday() >= 5  # Saturday=5, Sunday=6
        in_session = (not is_weekend) and open_m <= current_m < close_m
        minutes_since_open  = current_m - open_m  if in_session else None
        minutes_until_close = close_m - current_m if in_session else None

        if is_weekend:
            status = "closed_weekend"
        elif is_holiday:
            status = "closed_holiday"
        elif not in_session:
            status = "closed"
        elif minutes_since_open < 60:
            status = "opening_hour"
        elif minutes_until_close <= 60:
            status = "closing_hour"
        else:
            status = "active"

        sessions[name] = {
            "name":                name,
            "status":              status,
            "local_time":          local_dt.isoformat(),
            "minutes_since_open":  minutes_since_open,
            "minutes_until_close": minutes_until_close,
            "is_holiday":          is_holiday,
        }

    active_names = [
        n for n, s in sessions.items()
        if s["status"] not in ("closed", "closed_holiday", "closed_weekend")
    ]
    active_set = set(active_names)

    # Overlap
    if {"london", "new_york"} <= active_set:
        overlap = "london_newyork"
    elif {"tokyo", "london"} <= active_set:
        overlap = "tokyo_london"
    elif {"sydney", "tokyo"} <= active_set:
        overlap = "sydney_tokyo"
    elif len(active_set) <= 1:
        overlap = "none"
    else:
        overlap = "other"

    # Liquidity
    if not active_set:
        liquidity = "very_low"
    elif overlap == "london_newyork":
        liquidity = "very_high"
    elif overlap == "tokyo_london":
        liquidity = "high"
    elif "london" in active_set or "new_york" in active_set:
        major = [s for s in ("london", "new_york") if s in active_set]
        in_core = any(sessions[s]["status"] == "active" for s in major)
        liquidity = "high" if in_core else "medium"
    elif "tokyo" in active_set:
        liquidity = "medium"
    else:
        liquidity = "low"

    # Recommended action
    major_holiday = any(
        sessions[s]["is_holiday"]
        for s in ("london", "new_york")
        if sessions[s]["status"] == "closed_holiday"
    )
    any_transitional = any(
        sessions[s]["status"] in ("opening_hour", "closing_hour")
        for s in active_names
    )

    if liquidity == "very_low" or major_holiday:
        recommended_action = "avoid"
    elif liquidity == "medium" or any_transitional:
        recommended_action = "caution"
    else:
        recommended_action = "trade"

    result: dict[str, Any] = {
        "timestamp":      utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sessions":           sessions,
        "active_sessions":    active_names,
        "session_count":      len(active_names),
        "overlap":            overlap,
        "liquidity_estimate": liquidity,
        "recommended_action": recommended_action,
    }

    if pair:
        ctx = _pair_context(pair, sessions, active_names)
        if ctx:
            result["pair_context"] = ctx

    return result


class ForexSessionStatusTool(BaseTool):
    name = "get_session_status"
    description = (
        "Returns current Forex session status for Sydney, Tokyo, London, and New York. "
        "Includes active sessions, overlap detection, liquidity estimate (very_low → very_high), "
        "recommended action (trade / caution / avoid), and — when a pair is provided — "
        "pair-specific session relevance and liquidity. "
        "Uses zoneinfo for DST-accurate local times and the holidays library for bank holiday detection."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "timestamp": {
                "type": "string",
                "description": "Optional UTC timestamp in ISO 8601 format. Defaults to current time.",
            },
            "pair": {
                "type": "string",
                "description": (
                    "Optional currency pair (e.g. EURUSD). When provided, adds pair_context "
                    "with primary_sessions, active_primary, current_relevance, and pair_liquidity."
                ),
            },
        },
        "required": [],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        ts_raw = str(arguments.get("timestamp", "")).strip()
        utc_dt = (
            datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts_raw
            else datetime.now(UTC)
        )
        pair = str(arguments.get("pair", "")).strip() or (context.pair or "")
        return get_session_status(utc_dt, pair=pair or None)
