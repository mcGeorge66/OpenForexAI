"""One writer for routing rules, ownership decides who may change what.

Two writers on one file is how rules get lost: the designer saves the whole
file while a service appends its own entry and one silently wins. And a derived
rule whose source disappeared must not survive as an orphan that keeps routing
events nobody handles.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from openforexai.messaging.routing import RoutingRule
from openforexai.messaging.routing_store import RoutingRuleStore


def _rule(rule_id: str, event: str = "e", owner: str = "rule") -> RoutingRule:
    return RoutingRule(id=rule_id, event=event, to="SYSTM-ALL___-GA-NOTIFY", owner=owner)


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "event_routing.json5"
    path.write_text(json.dumps({"rules": [
        {"id": "hand_written", "event": "repo_request", "from": "*",
         "to": "SYSTM-ALL___-GA-REPO", "priority": 2, "description": "von Hand"},
    ]}), encoding="utf-8")
    return RoutingRuleStore(path)


async def test_hand_written_rules_default_to_the_designer_owner(store):
    assert [r.owner for r in store.all_rules()] == ["rule"]


async def test_replace_owner_adds_derived_rules_without_touching_hand_written(store):
    await store.replace_owner("telegram", [_rule("notify_order_result", owner="telegram")])

    owners = {r.id: r.owner for r in store.all_rules()}
    assert owners == {"hand_written": "rule", "notify_order_result": "telegram"}


async def test_replace_owner_removes_rules_whose_source_is_gone(store):
    """Deleting is just another modification — whatever is not in the new set goes."""
    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram"),
                                           _rule("notify_b", owner="telegram")])
    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])

    ids = {r.id for r in store.all_rules()}
    assert ids == {"hand_written", "notify_a"}


async def test_replace_owner_never_touches_another_owner(store):
    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])
    await store.replace_owner("other", [_rule("other_a", owner="other")])

    ids = {r.id for r in store.all_rules()}
    assert ids == {"hand_written", "notify_a", "other_a"}


async def test_replace_owner_refuses_to_delete_hand_written_rules(store):
    """Guard against a service wiping the designer's file via the same primitive."""
    with pytest.raises(ValueError):
        await store.replace_owner("rule", [])


async def test_unchanged_set_does_not_rewrite_the_file(store):
    """Rewriting on every startup would strip the file's comments for nothing."""
    rules = [_rule("notify_a", owner="telegram")]
    await store.replace_owner("telegram", rules)
    before = store._path.read_text(encoding="utf-8")
    mtime_before = store._path.stat().st_mtime_ns

    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])

    assert store._path.read_text(encoding="utf-8") == before
    assert store._path.stat().st_mtime_ns == mtime_before


async def test_change_triggers_the_reload_callback(tmp_path):
    """Saved config must take effect without a restart — enforced in one place."""
    path = tmp_path / "event_routing.json5"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    calls: list[int] = []

    async def _on_changed():
        calls.append(1)

    store = RoutingRuleStore(path, on_changed=_on_changed)
    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])
    assert calls == [1]

    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])
    assert calls == [1], "unveränderte Menge darf keinen Reload auslösen"


async def test_designer_save_keeps_service_owned_rules(store):
    """The designer may replace everything it owns — and nothing it does not."""
    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])

    await store.save_designer_rules([_rule("new_hand_written", event="x")])

    owners = {r.id: r.owner for r in store.all_rules()}
    assert owners == {"new_hand_written": "rule", "notify_a": "telegram"}


async def test_written_file_stays_parsable(store):
    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])
    import json5
    assert len(json5.loads(store._path.read_text(encoding="utf-8"))["rules"]) == 2


async def test_write_keeps_other_top_level_keys(tmp_path):
    """The store owns the rule list, not the whole document."""
    path = tmp_path / "event_routing.json5"
    path.write_text(json.dumps({"version": 3, "rules": []}), encoding="utf-8")
    store = RoutingRuleStore(path)

    await store.replace_owner("telegram", [_rule("notify_a", owner="telegram")])

    import json5
    assert json5.loads(path.read_text(encoding="utf-8"))["version"] == 3


def test_one_store_per_file(tmp_path):
    """A second instance would bring a second lock — i.e. two writers again."""
    from openforexai.messaging.routing_store import get_routing_store

    path = tmp_path / "event_routing.json5"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")

    first = get_routing_store(path)
    assert get_routing_store(path) is first
    # A relative/unresolved path must not produce a second store for the same file.
    assert get_routing_store(Path(str(path))) is first


# ── The rule designer goes through the same store ─────────────────────────────

async def test_designer_save_via_api_keeps_derived_rules(tmp_path, monkeypatch):
    """The designer sees derived rules; saving must not turn them into its own."""
    from openforexai.management import api
    from openforexai.messaging.routing_store import _stores, get_routing_store

    path = tmp_path / "event_routing.json5"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    _stores.clear()
    store = get_routing_store(path)
    await store.replace_owner("telegram", [_rule("notify_order_result", owner="telegram")])

    monkeypatch.setattr(api, "_bus", None)
    monkeypatch.setattr(api, "_routing_table", None)

    # The UI posts back everything it displayed, derived rules included.
    payload = {"rules": [
        {"id": "hand_written", "event": "repo_request", "from": "*",
         "to": "SYSTM-ALL___-GA-REPO", "priority": 2},
        {"id": "notify_order_result", "event": "order_result", "from": "*",
         "to": "SYSTM-ALL___-GA-NOTIFY", "priority": 50, "owner": "telegram"},
    ]}
    result = await api._save_designer_routing_rules(path, payload)

    assert result["rules_saved"] == 1
    assert result["derived_rules_unchanged"] == ["notify_order_result"]
    owners = {r.id: r.owner for r in store.all_rules()}
    assert owners == {"hand_written": "rule", "notify_order_result": "telegram"}


async def test_designer_save_via_api_cannot_delete_a_derived_rule(tmp_path, monkeypatch):
    """Dropping it from the payload must not remove what the designer does not own."""
    from openforexai.management import api
    from openforexai.messaging.routing_store import _stores, get_routing_store

    path = tmp_path / "event_routing.json5"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    _stores.clear()
    store = get_routing_store(path)
    await store.replace_owner("telegram", [_rule("notify_order_result", owner="telegram")])

    monkeypatch.setattr(api, "_bus", None)
    monkeypatch.setattr(api, "_routing_table", None)

    await api._save_designer_routing_rules(path, {"rules": []})

    assert [r.id for r in store.all_rules()] == ["notify_order_result"]
