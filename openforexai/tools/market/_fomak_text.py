"""Plain-language FOMAK explanations — ported from fomak_analyse.py (external
Fomak_service project), trimmed to what compute_fomak needs: parsing/validating
a FOMAK code and explaining it (component-by-component and as one condensed
interpretation). explain_parameter_change (before/after comparison) intentionally
left out for now — not needed yet, can be ported later if useful.
"""
from __future__ import annotations

import re
from typing import Any

_FOMAK_PATTERN = re.compile(
    r"^(?P<S_bin>\d)(?P<D_char>[UDN])(?P<V_bin>\d)(?P<P_bin>\d)(?P<I_bin>\d)(?P<A_char>[SOUDN])$"
)


class FomakParseError(ValueError):
    pass


def parse_fomak(fomak: str) -> dict[str, str]:
    m = _FOMAK_PATTERN.match(fomak.strip())
    if not m:
        raise FomakParseError(f"Invalid FOMAK string: '{fomak}'")
    parts = m.groupdict()
    _validate_da_combo(parts["D_char"], parts["A_char"])
    return parts


def _validate_da_combo(d_char: str, a_char: str) -> None:
    """Checked against every (d_char, higher_dir) pair alignment_char() can actually
    produce (see _fomak_core.py): A='O' never pairs with D='N', A in {'U','D'} only
    ever pairs with D='N'. A='S' legitimately pairs with ANY d_char, including 'N'
    (both the block and the higher timeframe are neutral — "consistently flat")."""
    if a_char == "O" and d_char == "N":
        raise FomakParseError("Invalid D/A combination: A='O' implies D must be 'U' or 'D', got 'N'")
    if a_char in ("U", "D") and d_char != "N":
        raise FomakParseError(f"Invalid D/A combination: A='{a_char}' implies D must be 'N', got '{d_char}'")


_S_DESC = {1: "low trend strength - hardly any to slightly directional movement.",
           2: "medium trend strength - a clear but not dominant drift.",
           3: "high to extreme trend strength - strong to very large net move."}
_V_DESC = {1: "low volatility - quiet to below-average market.",
           2: "normal volatility - typical range.",
           3: "elevated to very high volatility - larger swings to strong spikes."}
_P_DESC = {1: "low persistence - frequent direction changes, trend attempts often interrupted.",
           2: "medium persistence - some trend, but with pullbacks.",
           3: "high to extreme persistence - most to almost all candles moving in the same direction."}
_I_DESC = {1: "almost no to light impulse - no strong acceleration phases.",
           2: "moderate impulse - clear movement phases without extremes.",
           3: "strong to very strong impulse - powerful to explosive moves."}
_DIR_TEXT = {"U": "upwards (bullish)", "D": "downwards (bearish)", "N": "neutral / flat"}
_A_TEXT = {"S": "direction is aligned with the higher-timeframe trend.",
           "O": "direction is opposite to the higher-timeframe trend.",
           "U": "no direction in block, higher-timeframe trend up.",
           "D": "no direction in block, higher-timeframe trend down.",
           "N": "higher-timeframe trend neutral or unclear."}


def explain_fomak(fomak: str) -> str:
    """Component-by-component explanation (S/V/P/I/D/A each described)."""
    p = parse_fomak(fomak)
    s_bin, v_bin, p_bin, i_bin = (int(p[k]) for k in ("S_bin", "V_bin", "P_bin", "I_bin"))
    d_char, a_char = p["D_char"], p["A_char"]

    return (
        f"FOMAK {fomak} describes a market that is overall {_DIR_TEXT[d_char]}.\n\n"
        f"S (Trend strength): {s_bin} --> {_S_DESC[s_bin]}\n"
        f"V (Volatility):     {v_bin} --> {_V_DESC[v_bin]}\n"
        f"P (Persistence):    {p_bin} --> {_P_DESC[p_bin]}\n"
        f"I (Impulse):        {i_bin} --> {_I_DESC[i_bin]}\n"
        f"A (Alignment):      {a_char} --> {_A_TEXT[a_char]}"
    )


def interpret_fomak(fomak: str) -> str:
    """Condensed, semantic interpretation — a short readable market description."""
    p = parse_fomak(fomak)
    s_bin, v_bin, p_bin, i_bin = (int(p[k]) for k in ("S_bin", "V_bin", "P_bin", "I_bin"))
    d_char, a_char = p["D_char"], p["A_char"]

    d_sign = {"U": 1, "D": -1, "N": 0}[d_char]
    if a_char == "S":
        a_sign = d_sign
    elif a_char == "O":
        a_sign = -d_sign if d_sign != 0 else 0
    elif a_char == "U":
        a_sign = 1
    elif a_char == "D":
        a_sign = -1
    else:
        a_sign = 0

    direction = {"U": "upwards", "D": "downwards", "N": "sideways / neutral"}[d_char]
    bias = {"U": "bullish", "D": "bearish", "N": "neutral"}[d_char]
    higher_bias = {
        "S": "the higher timeframe trend supports this direction",
        "O": "the higher timeframe trend points the other way",
        "U": "block neutral, higher timeframe trend up",
        "D": "block neutral, higher timeframe trend down",
        "N": "the higher timeframe trend is neutral or unclear",
    }[a_char]

    if s_bin >= 3 and p_bin >= 2:
        regime = "a strong and relatively clean trending market"
    elif s_bin >= 3:
        regime = "a strong but noisy trend or acceleration phase"
    elif s_bin <= 1 and p_bin <= 1:
        regime = "a sideways, range-bound market"
    elif v_bin >= 3 and p_bin <= 1:
        regime = "a chaotic, high-volatility market phase"
    else:
        regime = "a moderately trending market without a clear extreme condition"

    header = f"The current FOMAK {fomak} describes {regime}, moving mostly {direction} ({bias}) - {higher_bias}."

    comments = []
    if i_bin >= 3:
        comments.append("Current moves have strong impulse character; breakouts and fast pushes are likely.")
    elif i_bin <= 1:
        comments.append("Impulse is currently weak - moves can easily stall.")
    if d_sign != 0 and a_sign != 0 and d_sign != a_sign:
        comments.append("The current move runs against the higher-timeframe trend - more likely a correction.")
    elif d_sign != 0 and a_sign != 0 and d_sign == a_sign:
        comments.append("Short-term and higher-timeframe trend direction are aligned.")
    return header + ("\n" + " ".join(comments) if comments else "")
