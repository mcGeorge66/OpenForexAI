from __future__ import annotations

import pytest

from openforexai.tools.market._fomak_text import (
    FomakParseError,
    explain_fomak,
    interpret_fomak,
    parse_fomak,
)


def test_parse_valid_fomak():
    parts = parse_fomak("3U2231S")
    assert parts == {"S_bin": "3", "D_char": "U", "V_bin": "2", "P_bin": "2", "I_bin": "3", "N_bin": "1", "A_char": "S"}


def test_parse_rejects_malformed_string():
    with pytest.raises(FomakParseError):
        parse_fomak("not-a-fomak")


@pytest.mark.parametrize("fomak", ["1NS4S", "3U2223U"])
def test_parse_rejects_invalid_d_a_combo_or_shape(fomak):
    with pytest.raises(FomakParseError):
        parse_fomak(fomak)


def test_explain_fomak_de_mentions_all_components():
    text = explain_fomak("3U2231S", lang="de")
    for label in ("Trendstärke", "Volatilität", "Persistenz", "Impuls", "Noise", "Alignment"):
        assert label in text


def test_explain_fomak_en():
    text = explain_fomak("3U2231S", lang="en")
    assert "trend" in text.lower()
    assert "3U2231S" in text


def test_interpret_fomak_returns_nonempty_text_both_languages():
    de = interpret_fomak("3U2231S", lang="de")
    en = interpret_fomak("3U2231S", lang="en")
    assert de and en
    assert "3U2231S" in de
    assert "3U2231S" in en


def test_interpret_range_market():
    text = interpret_fomak("1N1121S", lang="de")
    assert "Range" in text or "seitwärts" in text.lower()
