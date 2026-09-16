"""A missing barrier is a statement, not an empty field.

Measured on production data before this change: 2212 of 27971 USDJPY candles
(7.9 %) carried no FOPOK at all, because price stood beyond everything the
level search found in its 25-hour lookback. Five of six sampled had no
resistance above — a new high. They cluster in the active hours (10-13 % at
13:00-18:00 UTC), which is the trending situation the same day's measurements
identified as the only profitable one.

An empty field cannot be told apart from a bug, a data gap or a crash. `O`
says which side is open, so a prompt selector can match on "free path upwards"
instead of having to invent a rule for "nothing there".
"""
from __future__ import annotations

import pytest

from openforexai.tools.market._fopok_core import (
    FopokInputError,
    compute_fopok,
    explain_fopok,
)

RES = {"price": 155.35, "touch_count": 1}
SUP = {"price": 155.00, "touch_count": 4}


def test_both_barriers_unchanged() -> None:
    """The ordinary case must be untouched by the new state."""
    r = compute_fopok(current_price=155.20, nearest_resistance=RES,
                      nearest_support=SUP, atr=0.15)
    assert r["fopok"] == "MWFEN"
    assert r["raw_values"]["room_up_atr"] == 1.0
    assert r["raw_values"]["room_down_atr"] == 1.33


def test_no_resistance_reads_open_above() -> None:
    r = compute_fopok(current_price=157.636, nearest_resistance=None,
                      nearest_support={"price": 157.159, "touch_count": 1}, atr=0.12)
    pos, width, above, below, _ = r["fopok"]
    assert (pos, width, above, below) == ("X", "X", "O", "F")
    assert r["raw_values"]["room_up_atr"] is None
    assert r["raw_values"]["room_down_atr"] is not None


def test_no_support_reads_open_below() -> None:
    r = compute_fopok(current_price=161.969,
                      nearest_resistance={"price": 162.242, "touch_count": 4},
                      nearest_support=None, atr=0.10)
    pos, width, above, below, _ = r["fopok"]
    assert (pos, width, above, below) == ("X", "X", "E", "O")
    assert r["raw_values"]["room_down_atr"] is None


def test_undefined_corridor_is_not_invented() -> None:
    """With one side open there is no corridor — the fields say so rather
    than carrying a number that would look measured."""
    r = compute_fopok(current_price=157.6, nearest_resistance=None,
                      nearest_support={"price": 157.1, "touch_count": 1}, atr=0.12)
    assert r["raw_values"]["corridor_pips_in_atr"] is None
    assert r["raw_values"]["position_in_corridor"] is None
    assert r["raw_values"]["resistance"] is None
    assert r["raw_values"]["resistance_touches"] is None


def test_nothing_at_all_still_refuses() -> None:
    """No level on either side is genuinely nothing to say — that must not
    silently become a code."""
    with pytest.raises(FopokInputError):
        compute_fopok(current_price=155.2, nearest_resistance=None,
                      nearest_support=None, atr=0.15)


def test_zero_atr_still_refuses() -> None:
    with pytest.raises(FopokInputError):
        compute_fopok(current_price=155.2, nearest_resistance=RES,
                      nearest_support=SUP, atr=0.0)


def test_inconsistent_structure_still_refuses() -> None:
    with pytest.raises(FopokInputError):
        compute_fopok(current_price=155.2, nearest_resistance={"price": 155.0},
                      nearest_support={"price": 155.35}, atr=0.15)


@pytest.mark.parametrize("code", ["XXOFN", "XXEON", "MWFEN", "UTFFA", "DNEEC"])
def test_every_code_can_be_read_out(code: str) -> None:
    text = explain_fopok(code)
    assert code in text
    assert len(text.splitlines()) >= 3


def test_open_case_says_what_was_found_not_what_is_missing() -> None:
    """This text is what the memory search compares.

    "only a lower barrier found" is one searchable phrase; spreading the same
    fact over "no level above" plus "barrier below is fresh" matches neither.
    """
    up = explain_fopok("XXOFN")
    assert "only a lower barrier found" in up
    assert "new high" in up

    down = explain_fopok("XXEON")
    assert "only an upper barrier found" in down
    assert "new low" in down

    # And the contradiction the first attempt produced must stay gone.
    assert "in no corridor" not in up


def test_unknown_character_is_rejected() -> None:
    with pytest.raises(FopokInputError):
        explain_fopok("ZZZZZ")


def test_format_version_travels_in_the_parameter_set() -> None:
    """A character that changed meaning must not be readable as if it had not.

    The stored key rows are addressed by parameter set; without the version in
    it, codes from before this change would be read as if `X` and `O` had
    always existed.
    """
    from openforexai.data.market_keys import param_set
    ps = param_set(timeframe="M5", lookback_candles=24, higher_timeframe="M30")
    assert ps.endswith("-p2")


def test_a_row_without_a_code_still_says_why() -> None:
    """The rule we agreed on: an empty field is not an acceptable answer.

    The first backfill left 78 rows blank. They looked like a market state —
    price beyond all structure — and were in fact the script skipping the
    start of the series for want of higher-timeframe bars. Nothing in the row
    distinguished the two.
    """
    from openforexai.data.market_keys import COLUMNS, row_for

    row = dict(zip(COLUMNS, row_for(
        timestamp="2026-05-04T17:30:00+00:00", params="p", fomak="2U332S",
        raw_values=None, computed_at="now",
        fopok=None, fopok_reason="not computed: only 4 M15 bars available",
    )))
    assert row["fopok"] is None
    assert "only 4 M15 bars" in row["fopok_text"]


def test_a_missing_reason_is_itself_reported() -> None:
    """Even forgetting to pass a reason must not produce a silent blank."""
    from openforexai.data.market_keys import COLUMNS, row_for

    row = dict(zip(COLUMNS, row_for(
        timestamp="t", params="p", fomak="2U332S", raw_values=None,
        computed_at="now", fopok=None,
    )))
    assert row["fopok_text"] == "not computed: no reason recorded"
