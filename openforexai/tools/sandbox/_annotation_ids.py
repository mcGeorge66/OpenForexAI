"""Shared helper: short, session-unique annotation ids for the PWB sandbox tools.

zone_marker/trade_marker/candle_marker all identify their annotation with an id
(zone_id/trade_id/marker_id). Ids are kept to at most 2 alphanumeric characters
(36^2 = 1296 combinations) so they stay readable as a chart-label prefix (e.g.
"[A1] Uptrend") the user can reference back in chat ("look at zone A1").
"""
from __future__ import annotations

import string
from typing import Any

_ALPHABET = string.ascii_uppercase + string.digits  # 36 chars -> 1296 two-char ids

_ID_FIELDS = ("zone_id", "trade_id", "marker_id")


def collect_used_ids(context_extra: dict[str, Any]) -> set[str]:
    """All ids already in play this session: prior turns (existing_annotations) plus
    whatever this turn has produced so far (workbench_annotations)."""
    used: set[str] = set()
    for annotation in (*context_extra.get("existing_annotations", []), *context_extra.get("workbench_annotations", [])):
        for field in _ID_FIELDS:
            value = annotation.get(field)
            if value:
                used.add(str(value).upper())
    return used


def next_free_id(used_ids: set[str]) -> str | None:
    for a in _ALPHABET:
        for b in _ALPHABET:
            candidate = f"{a}{b}"
            if candidate not in used_ids:
                return candidate
    return None  # all 1296 combinations taken — practically unreachable in one sandbox session


def resolve_new_id(explicit_id: str, used_ids: set[str]) -> tuple[str | None, str | None]:
    """For op='new': validate an explicit id, or auto-assign a free short one.
    Returns (id, error)."""
    explicit_id = explicit_id.strip()
    if not explicit_id:
        generated = next_free_id(used_ids)
        if generated is None:
            return None, "No short annotation ids left (all 1296 combinations already used this session)."
        return generated, None
    if len(explicit_id) > 2 or not explicit_id.isalnum():
        return None, f"Invalid id {explicit_id!r}: must be at most 2 alphanumeric characters (e.g. 'A1', '7K')."
    candidate = explicit_id.upper()
    if candidate in used_ids:
        return None, f"id {candidate!r} is already in use this session — pick another, or use op='change'/'delete' to correct it."
    return candidate, None


def resolve_existing_id(explicit_id: str, used_ids: set[str]) -> tuple[str | None, str | None]:
    """For op='change'/'delete': the id must already exist. Returns (id, error)."""
    explicit_id = explicit_id.strip()
    if not explicit_id:
        return None, "id is required for op='change'/'delete' (use get_annotation to look it up if you forgot it)."
    candidate = explicit_id.upper()
    if candidate not in used_ids:
        return None, f"No existing annotation with id {candidate!r} found this session — use op='new' to create one."
    return candidate, None
