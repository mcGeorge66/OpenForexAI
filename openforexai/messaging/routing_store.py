"""Single point of access for routing rules — used by the rule designer and by
services that derive rules of their own.

Two writers on one file is how rules get silently lost: the designer saves the
whole file while a service appends its own entry, and one of them wins. Routing
both through here means there is exactly one writer, one validation step and one
hot-reload trigger, no matter who asks.

Ownership decides who may change what. ``owner="rule"`` marks hand-authored
entries, which only the designer touches. Any other value names the service that
derives those rules; it replaces its own set wholesale via
:meth:`replace_owner`, so adding, changing and removing are the same operation —
whatever is not in the new set disappears, and orphans left behind by a deleted
source rule cannot exist.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import json5

from openforexai.messaging.routing import RoutingRule, rule_to_dict
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)

DESIGNER_OWNER = "rule"

_stores: dict[Path, "RoutingRuleStore"] = {}


def get_routing_store(path: Path, on_changed: Any = None) -> "RoutingRuleStore":
    """Return the one store responsible for *path*, creating it on first use.

    One instance per file, process-wide: a second instance would carry its own
    lock, which is exactly the two-writers race the store exists to prevent.
    The first caller (bootstrap) supplies the hot-reload callback; later callers
    (the management API) just get the same object.
    """
    key = Path(path).resolve()
    store = _stores.get(key)
    if store is None:
        store = RoutingRuleStore(key, on_changed=on_changed)
        _stores[key] = store
    elif on_changed is not None and store._on_changed is None:
        store._on_changed = on_changed
    return store


class RoutingRuleStore:
    """Reads and writes the routing rule file; serializes all access."""

    def __init__(self, path: Path, on_changed: Any = None) -> None:
        self._path = Path(path)
        # Called after every successful write so the live table picks the
        # change up — the project rule is that a saved config takes effect
        # without a restart, and putting it here means no caller can forget it.
        self._on_changed = on_changed
        self._lock = asyncio.Lock()

    # ── Reading ───────────────────────────────────────────────────────────────

    def read_raw(self) -> dict:
        if not self._path.exists():
            return {"rules": []}
        return json5.loads(self._path.read_text(encoding="utf-8"))

    def all_rules(self) -> list[RoutingRule]:
        from openforexai.messaging.routing import _rules_from_dict
        return _rules_from_dict(self.read_raw())

    def rules_by_owner(self, owner: str) -> list[RoutingRule]:
        return [r for r in self.all_rules() if r.owner == owner]

    # ── Writing ───────────────────────────────────────────────────────────────

    async def replace_owner(self, owner: str, rules: list[RoutingRule]) -> int:
        """Make *rules* the complete set owned by *owner*.

        Add, change and delete in one operation: everything previously owned by
        *owner* is dropped first, so a rule whose source disappeared cannot
        survive as an orphan that keeps routing events nobody handles.

        Returns the number of rules now owned by *owner*.
        """
        if owner == DESIGNER_OWNER:
            raise ValueError(
                "replace_owner must not be used for hand-authored rules — "
                "that would delete the designer's entries."
            )
        async with self._lock:
            current = self.all_rules()
            for rule in rules:
                rule.owner = owner
            # Idempotent: rewriting an unchanged file on every startup would
            # re-serialize it each time and strip the hand-written comments for
            # no reason. Only a real change to the owned set touches the file.
            mine = [rule_to_dict(r) for r in current if r.owner == owner]
            wanted = [rule_to_dict(r) for r in rules]
            if mine == wanted:
                return len(rules)
            existing = [r for r in current if r.owner != owner]
            await self._write(existing + list(rules))
        if self._on_changed is not None:
            await self._on_changed()
        return len(rules)

    async def save_designer_rules(self, rules: list[RoutingRule]) -> None:
        """Replace the hand-authored rules, leaving service-owned ones untouched."""
        async with self._lock:
            derived = [r for r in self.all_rules() if r.owner != DESIGNER_OWNER]
            for rule in rules:
                rule.owner = DESIGNER_OWNER
            await self._write(list(rules) + derived)
        if self._on_changed is not None:
            await self._on_changed()

    async def _write(self, rules: list[RoutingRule]) -> None:
        # Keep any other top-level keys the file carries — the store owns the
        # rule list, not the whole document.
        raw = self.read_raw()
        payload = {k: v for k, v in raw.items() if k != "rules"}
        payload["rules"] = [rule_to_dict(r) for r in sorted(rules, key=lambda r: r.priority)]
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        json5.loads(text)  # never leave an unparsable rule file behind
        await asyncio.to_thread(self._write_atomic, text)
        _log.info("Routing rules written", path=str(self._path), rules=len(rules))

    def _write_atomic(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._path)
