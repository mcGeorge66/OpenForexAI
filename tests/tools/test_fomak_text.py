from __future__ import annotations

import pytest

from openforexai.tools.market._fomak_text import (
    FomakParseError,
    explain_fomak,
    interpret_fomak,
    parse_fomak,
)


def test_parse_valid_fomak():
    parts = parse_fomak("3U223S")
    assert parts == {"S_bin": "3", "D_char": "U", "V_bin": "2", "P_bin": "2", "I_bin": "3", "A_char": "S"}


def test_parse_rejects_malformed_string():
    with pytest.raises(FomakParseError):
        parse_fomak("not-a-fomak")


@pytest.mark.parametrize("fomak", ["1NS4S", "3U222U"])
def test_parse_rejects_invalid_d_a_combo_or_shape(fomak):
    with pytest.raises(FomakParseError):
        parse_fomak(fomak)


def test_explain_fomak_mentions_all_components():
    text = explain_fomak("3U223S")
    for label in ("Trend strength", "Volatility", "Persistence", "Impulse", "Alignment"):
        assert label in text
    assert "Noise" not in text
    assert "3U223S" in text


def test_explain_fomak_is_english_only():
    """These texts are handed to a model, and the models are addressed in
    English throughout — the German variant and the lang switch were removed
    so no code path can put German in front of one."""
    text = explain_fomak("3U223S") + interpret_fomak("3U223S")
    assert not any(ch in text for ch in "äöüßÄÖÜ")


def test_interpret_fomak_returns_nonempty_text():
    text = interpret_fomak("3U223S")
    assert text
    assert "3U223S" in text


def test_interpret_range_market():
    text = interpret_fomak("1N112S")
    assert "range" in text.lower() or "sideways" in text.lower()
