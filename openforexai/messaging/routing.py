"""Event routing table — loads rules from JSON5, resolves message targets.

Rule file format (``config/RunTime/event_routing.json5``)::

    {
      "rules": [
        {
          "id":          "unique_rule_id",
          "description": "Human-readable comment",
          "event":       "m5_candle_available",   // EventType.value or "*"
          "from":        "OANDA-*-AA-*",          // sender agent-id pattern or "*"
          "to":          "SYSTM-ALL___-GA-DATA1", // target (see below)
          "priority":    100                       // lower number = higher priority
        }
      ]
    }

``to`` target types
-------------------
Literal agent ID
    ``"OANDA-ALL___-BA-SUP1"``
    Message is delivered to that single registered agent.

Template
    ``"OANDA-{sender.pair}-AA-TRD1"``
    Placeholders are substituted from the sender's parsed AgentId.
    Supported: ``{sender.broker}``, ``{sender.pair}``, ``{sender.type}``,
    ``{sender.name}``, ``{sender.extension}``, ``{sender.id}``.

Broadcast pattern (contains '*')
    ``"*-EURUSD-AA-*"``
    Message is fanned out to all *registered* agents whose ID matches the pattern.

``"*"`` (asterisk only)
    Broadcast to all registered agents.

``"@handlers"`` (special)
    Deliver only to legacy handler-subscribers (no queue-based delivery).
    Useful for infrastructure components (DataContainer, BrokerBase) that use
    the backward-compat ``subscribe()`` API.

Priority
--------
Rules are evaluated in ascending priority order (lowest number first).
Multiple rules can match the same message — ALL matching rules are applied
and the union of their resolved targets receives the message.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import json5

from openforexai.messaging.agent_id import AgentId, substitute_template
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)


@dataclass
class RoutingRule:
    """A single routing rule loaded from JSON5."""

    id: str
    event: str                 # EventType.value or "*"
    to: str                    # target expression
    from_pattern: str = "*"    # sender agent-id pattern
    description: str = ""
    priority: int = 100

    # ── Matching ──────────────────────────────────────────────────────────────

    def matches_event(self, event_value: str) -> bool:
        """Return True if this rule applies to *event_value*."""
        return self.event == "*" or self.event == event_value

    def matches_sender(self, sender_id: str) -> bool:
        """Return True if *sender_id* satisfies the from-pattern."""
        if self.from_pattern == "*":
            return True
        aid = AgentId.try_parse(sender_id)
        if aid is None:
            # Infrastructure senders (non-structured IDs) match only "*"
            return self.from_pattern == "*"
        return aid.matches(self.from_pattern)

    def matches(self, event_value: str, sender_id: str) -> bool:
        return self.matches_event(event_value) and self.matches_sender(sender_id)

    # ── Target resolution ─────────────────────────────────────────────────────

    def resolve_targets(
        self,
        sender_id: str,
        registered_agents: dict[str, object],  # agent_id → queue (or sentinel)
    ) -> list[str]:
        """Return the list of target agent IDs this rule resolves to.

        Returns an empty list if no target could be resolved or if this rule
        uses ``"@handlers"`` (handled separately by the bus).
        """
        target = self.to.strip()

        if target == "@handlers":
            return []  # handled via legacy subscribe() path

        # Broadcast all
        if target == "*":
            return list(registered_agents.keys())

        # Template substitution
        sender_aid = AgentId.try_parse(sender_id)
        if sender_aid is not None and "{sender." in target:
            target = substitute_template(target, sender_aid)

        # Wildcard broadcast pattern
        if "*" in target:
            matched = []
            for agent_id in registered_agents:
                aid = AgentId.try_parse(agent_id)
                if aid is not None and aid.matches(target):
                    matched.append(agent_id)
                elif agent_id == target:
                    matched.append(agent_id)
            return matched

        # Literal
        if target in registered_agents:
            return [target]

        # Target not registered — warn but do not crash
        _log.debug(
            "Routing rule %r resolved target %r but agent not registered", self.id, target
        )
        return []


# ── Routing table ─────────────────────────────────────────────────────────────

class RoutingTable:
    """Loaded and queryable routing rule table.

    Thread-safe for reads; hot-reload via ``reload()`` swaps the rule list
    atomically (Python GIL-safe list replacement).
    """

    def __init__(self) -> None:
        self._rules: list[RoutingRule] = []
        self._path: Path | None = None

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self, path: Path) -> None:
        """Load routing rules from *path* (JSON5).  Replaces any existing rules."""
        self._path = path
        self._rules = _parse_rules(path)
        _log.info("Routing table loaded", rules=len(self._rules), path=str(path))

    def reload(self) -> None:
        """Hot-reload from the file path used in the last ``load()`` call."""
        if self._path is None:
            raise RuntimeError("No routing file loaded yet; call load() first.")
        self._rules = _parse_rules(self._path)
        _log.info("Routing table reloaded", rules=len(self._rules), path=str(self._path))

    def load_dict(self, data: dict) -> None:
        """Load routing rules from an already-parsed dict (useful for testing)."""
        self._rules = _rules_from_dict(data)

    # ── Resolution ────────────────────────────────────────────────────────────

    def resolve(
        self,
        event_value: str,
        sender_id: str,
        registered_agents: dict[str, object],
    ) -> tuple[list[str], bool]:
        """Return ``(target_agent_ids, deliver_to_handlers)``.

        *target_agent_ids* — deduplicated list of registered agent IDs that
            should receive this message (queue-based delivery).

        *deliver_to_handlers* — True if at least one matching rule has
            ``"to": "@handlers"`` (legacy handler delivery).

        If no rule matches, returns ``([], False)`` — the bus will log a
        MonitoringBus warning and discard the message.
        """
        targets: dict[str, None] = {}  # ordered set
        has_handler_rule = False
        matched_any = False

        for rule in self._rules:  # already sorted by priority
            if not rule.matches(event_value, sender_id):
                continue
            matched_any = True
            if rule.to.strip() == "@handlers":
                has_handler_rule = True
            else:
                for t in rule.resolve_targets(sender_id, registered_agents):
                    targets[t] = None

        return list(targets.keys()), has_handler_rule, matched_any

    @property
    def rules(self) -> list[RoutingRule]:
        return list(self._rules)


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_rules(path: Path) -> list[RoutingRule]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json5.loads(text)
    except FileNotFoundError:
        _log.warning("Routing file not found: %s — using empty table", path)
        return []
    except ValueError as exc:
        _log.error("Invalid JSON5 in routing file %s: %s", path, exc)
        return []
    return _rules_from_dict(data)


def _rules_from_dict(data: dict) -> list[RoutingRule]:
    raw_rules = data.get("rules", [])
    rules: list[RoutingRule] = []
    for idx, raw in enumerate(raw_rules):
        try:
            rule = RoutingRule(
                id=raw.get("id", f"rule_{idx:04d}"),
                description=raw.get("description", ""),
                event=raw.get("event", "*"),
                from_pattern=raw.get("from", "*"),
                to=raw.get("to", ""),
                priority=int(raw.get("priority", 100)),
            )
            if not rule.to:
                _log.warning("Rule %r has empty 'to' field — skipping", rule.id)
                continue
            rules.append(rule)
        except Exception as exc:
            _log.error("Error parsing routing rule at index %d: %s — skipping", idx, exc)

    rules.sort(key=lambda r: r.priority)
    return rules






