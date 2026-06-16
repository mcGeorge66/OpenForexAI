from __future__ import annotations

from typing import Any


# =============================================================================
# PRIMITIVE UTILITIES
# =============================================================================

def _round_value(value: Any, digits: int = 6) -> float | None:
    # Safely coerces any value to float and rounds it. Returns None for
    # anything that cannot be converted (None, non-numeric strings, etc.).
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


# =============================================================================
# SERIES & INDICATOR HELPERS
#
# These functions operate on ordered lists of numeric values produced by the
# calculate_indicator tool. They are exposed to transform scripts as helpers.
# =============================================================================

def latest_value(values: list[Any]) -> float | None:
    # Returns the last non-None, non-NaN numeric value from a series list.
    # Iterates in reverse so that any trailing None entries are skipped.
    for item in reversed(values or []):
        rounded = _round_value(item, 6)
        if rounded is not None:
            return rounded
    return None


def classify_series_direction(values: list[Any], change_threshold: float = 1e-6) -> str:
    # Classifies a numeric series as "rising", "falling", or "flat" by
    # comparing the last element to the first.
    numeric = [_round_value(item, 6) for item in (values or [])]
    numeric = [item for item in numeric if item is not None]
    if len(numeric) < 2:
        return "flat"
    delta = float(numeric[-1]) - float(numeric[0])
    if delta > change_threshold:
        return "rising"
    if delta < -change_threshold:
        return "falling"
    return "flat"


def classify_indicator_direction(values: list[Any], indicator_name: str) -> str:
    # Wraps classify_series_direction with indicator-aware semantics:
    #   - RSI uses a larger flat threshold (0.1) to avoid noise.
    #   - ATR translates rising/falling into "expanding"/"contracting"/"stable".
    #   - All other indicators use the raw direction labels.
    indicator = str(indicator_name or "").upper()
    threshold = 0.1 if indicator == "RSI" else 1e-6
    direction = classify_series_direction(values, threshold)
    if indicator == "ATR":
        return "expanding" if direction == "rising" else ("contracting" if direction == "falling" else "stable")
    return direction


# =============================================================================
# TOOL OUTPUT NORMALIZATION
#
# Standardise the raw JSON returned by get_candles and calculate_indicator
# into the clean, uniform structures used in snapshot pipeline transform scripts.
# =============================================================================

def normalize_candle_tool_output(tool_output: Any, timeframe: str | None = None) -> list[dict[str, Any]]:
    # Converts the raw list of candle dicts returned by the get_candles tool
    # into a compact, normalised representation.
    rows = tool_output if isinstance(tool_output, list) else []
    normalized: list[dict[str, Any]] = []
    resolved_timeframe = str(timeframe or "M5").upper()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            normalized.append(
                {
                    "timestamp": row.get("timestamp"),
                    "open": _round_value(row.get("open")),
                    "high": _round_value(row.get("high")),
                    "low": _round_value(row.get("low")),
                    "close": _round_value(row.get("close")),
                    "spread": _round_value(row.get("spread"), 2),
                    "tick_volume": int(row.get("tick_volume", 0) or 0),
                    "timeframe": resolved_timeframe,
                }
            )
        except (TypeError, ValueError):
            continue
    return normalized


def build_indicator_tool_output(
    tool_output: Any,
    *,
    tool_input: dict[str, Any] | None = None,
    all_outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Normalises the raw dict returned by the calculate_indicator tool into a
    # consistent structure used in transform scripts.
    row = tool_output if isinstance(tool_output, dict) else {}
    input_row = tool_input if isinstance(tool_input, dict) else {}
    indicator_name = str(row.get("indicator") or input_row.get("indicator") or "").upper()
    period = row.get("period", input_row.get("period"))
    history = row.get("history", input_row.get("history"))
    values_raw = row.get("values")
    if values_raw is None:
        values_raw = row.get("value")
    points = values_raw if isinstance(values_raw, list) else []
    series: list[float] = []
    for item in points:
        raw_value = item.get("value") if isinstance(item, dict) else item
        rounded = _round_value(raw_value, 6)
        if rounded is not None:
            series.append(rounded)
    payload: dict[str, Any] = dict(row)
    payload["indicator"] = indicator_name or payload.get("indicator")
    payload["period"] = period
    payload["history"] = history
    payload["latest"] = latest_value(series)
    payload["direction"] = classify_indicator_direction(series, indicator_name)
    payload["values"] = points
    if "value" in payload:
        del payload["value"]
    return payload
