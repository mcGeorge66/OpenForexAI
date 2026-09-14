"""Declarative rules that turn bus events into notifications.

Adding a new warning should be a config change, not a code change — the bus is
the system's main artery, so anything worth alerting on is already travelling
on it. A rule names the event type, optionally filters on its content, and
renders title and text from the event's own fields.

Deliberately declarative: literals, patterns, numeric comparisons and
placeholders — no executable code in config. The EventComposer already exists
for anything that needs real logic; a second, weaker scripting layer hiding in
the notification config would be a mistake.

Rule shape::

    "order_result": {
      "severity": "critical",
      "title": "{instrument}: Order abgelehnt",
      "template": "{error}",
      "only_if": {"success": false, "error": {"regex": "returned None"}},
      "dedup_by": ["instrument"]
    }
"""
from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_.]+)\}")
_NUMERIC_OPS = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
}


def resolve_path(data: Any, path: str) -> Any:
    """Look up a dotted path, returning None instead of raising.

    Payloads in this system are nested (order.signal.pair), and a rule that
    references a field an event happens not to carry must degrade quietly —
    a notification is never important enough to break its own delivery.
    """
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return None
    return current


def render(template: str, data: dict[str, Any]) -> str:
    """Fill {placeholders} from *data*; unknown or missing fields become empty."""
    def _sub(match: re.Match[str]) -> str:
        value = resolve_path(data, match.group(1))
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(_sub, template)


def matches(condition: Any, value: Any) -> bool:
    """Check one field condition: literal, {regex}, or a numeric comparison."""
    if not isinstance(condition, dict):
        return value == condition

    for op, expected in condition.items():
        if op == "regex":
            if value is None or not re.search(str(expected), str(value)):
                return False
        elif op == "contains":
            if value is None or str(expected) not in str(value):
                return False
        elif op == "ne":
            if value == expected:
                return False
        elif op in _NUMERIC_OPS:
            try:
                if not _NUMERIC_OPS[op](float(value), float(expected)):
                    return False
            except (TypeError, ValueError):
                return False  # non-numeric value can't satisfy a numeric test
        else:
            return False  # unknown operator: fail closed rather than alert wrongly
    return True


def rule_applies(rule: dict[str, Any], data: dict[str, Any]) -> bool:
    """True when every only_if condition holds for this event."""
    conditions = rule.get("only_if")
    if not isinstance(conditions, dict) or not conditions:
        return True
    return all(matches(cond, resolve_path(data, field)) for field, cond in conditions.items())


def dedup_key_for(rule_name: str, rule: dict[str, Any], data: dict[str, Any]) -> str:
    """Build the suppression key.

    Without per-field keys every agent shares one key, so a EURUSD failure would
    silently swallow a simultaneous USDJPY failure — exactly the kind of quiet
    loss this channel exists to prevent.
    """
    fields = rule.get("dedup_by")
    if not isinstance(fields, list) or not fields:
        return rule_name
    parts = [str(resolve_path(data, str(f))) for f in fields]
    return rule_name + ":" + "|".join(parts)


def event_view(event_type: str, source: str, instrument: str | None,
               payload: dict[str, Any] | None) -> dict[str, Any]:
    """Fields a rule can reference: envelope data plus the payload itself.

    Envelope keys come first so payload fields of the same name win — the
    payload is the more specific source.
    """
    view: dict[str, Any] = {
        "event": event_type,
        "source": source,
        "instrument": instrument or "",
    }
    if isinstance(payload, dict):
        view.update(payload)
    return view
