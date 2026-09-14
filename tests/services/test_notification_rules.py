"""Rules decide what reaches the phone — so both directions must be pinned.

A rule that fires too often trains you to ignore the channel; a rule that never
fires is the 2026-09-14 incident again (ten rejected orders, nobody noticed).
"""
from __future__ import annotations

import pytest

from openforexai.services.notification_rules import (
    dedup_key_for,
    event_view,
    matches,
    render,
    resolve_path,
    rule_applies,
)


# ── Field access ──────────────────────────────────────────────────────────────

def test_resolves_nested_paths():
    data = {"order": {"signal": {"pair": "EURUSD"}}}
    assert resolve_path(data, "order.signal.pair") == "EURUSD"


def test_missing_path_yields_none_instead_of_raising():
    assert resolve_path({"a": 1}, "does.not.exist") is None


# ── Templates ─────────────────────────────────────────────────────────────────

def test_template_fills_nested_placeholders():
    data = {"instrument": "USDJPY", "order": {"units": 16770}}
    assert render("{instrument}: {order.units} Einheiten", data) == "USDJPY: 16770 Einheiten"


def test_missing_placeholder_renders_empty_and_never_raises():
    """A notification must not fail because a field was absent."""
    assert render("Grund: {error}", {"instrument": "EURUSD"}) == "Grund: "


def test_braces_in_content_do_not_break_rendering():
    assert render("{a}", {"a": "{nicht_ersetzt}"}) == "{nicht_ersetzt}"


# ── Conditions ────────────────────────────────────────────────────────────────

def test_literal_condition_matches_exactly():
    assert matches(False, False) is True
    assert matches(False, True) is False


def test_regex_condition():
    assert matches({"regex": "returned None"}, "MT5 order_send returned None (…)") is True
    assert matches({"regex": "returned None"}, "retcode=10019; No money") is False


def test_regex_on_missing_value_does_not_match():
    assert matches({"regex": "x"}, None) is False


@pytest.mark.parametrize("cond,value,expected", [
    ({"lt": -50}, -75.0, True),
    ({"lt": -50}, -10.0, False),
    ({"gte": 3}, 3, True),
    ({"gt": 3}, 3, False),
])
def test_numeric_comparisons(cond, value, expected):
    assert matches(cond, value) is expected


def test_numeric_condition_on_non_numeric_value_is_false():
    """Regex cannot express thresholds; thresholds must not blow up on text."""
    assert matches({"lt": 5}, "keine Zahl") is False


def test_unknown_operator_fails_closed():
    """Better a missing alert than a wrong one fired by a typo in config."""
    assert matches({"gibtsnicht": 1}, 1) is False


# ── Rule evaluation ───────────────────────────────────────────────────────────

def test_rule_without_conditions_always_applies():
    assert rule_applies({"severity": "critical"}, {"anything": 1}) is True


def test_all_conditions_must_hold():
    rule = {"only_if": {"success": False, "error": {"regex": "None"}}}
    assert rule_applies(rule, {"success": False, "error": "returned None"}) is True
    assert rule_applies(rule, {"success": False, "error": "No money"}) is False
    assert rule_applies(rule, {"success": True, "error": "returned None"}) is False


def test_successful_order_does_not_trigger_the_failure_rule():
    """order_result fires on every attempt — without the filter every winning
    trade would buzz the phone."""
    rule = {"only_if": {"success": False}}
    assert rule_applies(rule, {"success": True, "order_id": "12526681"}) is False


# ── Deduplication keys ────────────────────────────────────────────────────────

def test_dedup_by_separates_pairs():
    """Without this, a EURUSD failure would suppress a simultaneous USDJPY one."""
    rule = {"dedup_by": ["instrument"]}
    eur = dedup_key_for("order_result", rule, {"instrument": "EURUSD"})
    jpy = dedup_key_for("order_result", rule, {"instrument": "USDJPY"})
    assert eur != jpy


def test_dedup_defaults_to_the_rule_name():
    assert dedup_key_for("risk_breach", {}, {}) == "risk_breach"


# ── Envelope + payload view ───────────────────────────────────────────────────

def test_event_view_exposes_envelope_and_payload():
    view = event_view("order_result", "OXS_T-ALL___-BA-ANLYS", "EURUSD", {"success": False})
    assert view["event"] == "order_result"
    assert view["source"] == "OXS_T-ALL___-BA-ANLYS"
    assert view["instrument"] == "EURUSD"
    assert view["success"] is False


def test_payload_wins_over_envelope_on_name_clash():
    view = event_view("order_result", "src", "EURUSD", {"instrument": "USDJPY"})
    assert view["instrument"] == "USDJPY"
