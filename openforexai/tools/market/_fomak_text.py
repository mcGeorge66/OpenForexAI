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
    r"^(?P<S_bin>\d)(?P<D_char>[UDN])(?P<V_bin>\d)(?P<P_bin>\d)(?P<I_bin>\d)(?P<N_bin>\d)(?P<A_char>[SOUDN])$"
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


_S_DESC = {
    "de": {1: "geringe Trendstärke - kaum bis leicht gerichtete Bewegung.",
           2: "mittlere Trendstärke - klarer, aber nicht dominanter Drift.",
           3: "hohe bis extreme Trendstärke - deutliche bis sehr große Netto-Bewegung."},
    "en": {1: "low trend strength - hardly any to slightly directional movement.",
           2: "medium trend strength - a clear but not dominant drift.",
           3: "high to extreme trend strength - strong to very large net move."},
}
_V_DESC = {
    "de": {1: "niedrige Volatilität - ruhiger bis unterdurchschnittlicher Markt.",
           2: "normale Volatilität - typische Range.",
           3: "erhöhte bis sehr hohe Volatilität - größere Schwünge bis starke Spikes."},
    "en": {1: "low volatility - quiet to below-average market.",
           2: "normal volatility - typical range.",
           3: "elevated to very high volatility - larger swings to strong spikes."},
}
_P_DESC = {
    "de": {1: "geringe Persistenz - häufige Richtungswechsel, Trendversuche oft unterbrochen.",
           2: "mittlere Persistenz - etwas Trend, aber mit Rücksetzern.",
           3: "hohe bis extreme Persistenz - die meisten bis fast alle Kerzen laufen in dieselbe Richtung."},
    "en": {1: "low persistence - frequent direction changes, trend attempts often interrupted.",
           2: "medium persistence - some trend, but with pullbacks.",
           3: "high to extreme persistence - most to almost all candles moving in the same direction."},
}
_I_DESC = {
    "de": {1: "kaum bis leichter Impuls - keine ausgeprägten Beschleunigungsphasen.",
           2: "moderater Impuls - klare Bewegungsphasen ohne Extreme.",
           3: "starker bis sehr starker Impuls - kräftige bis explosive Bewegungen."},
    "en": {1: "almost no to light impulse - no strong acceleration phases.",
           2: "moderate impulse - clear movement phases without extremes.",
           3: "strong to very strong impulse - powerful to explosive moves."},
}
_N_DESC = {
    "de": {1: "wenig Rauschen - überwiegend saubere Kerzen, klare Struktur.",
           2: "mittleres Rauschen - Mischung aus sauberen und zappeligen Kerzen.",
           3: "hohes bis sehr hohes Rauschen - viele Spikes, hohes Whipsaw-Risiko."},
    "en": {1: "low noise - mostly clean candles, clear structure.",
           2: "medium noise - mix of clean and choppy candles.",
           3: "high to very high noise - many spikes, high whipsaw risk."},
}
_DIR_TEXT = {
    "de": {"U": "aufwärts (bullisch)", "D": "abwärts (bärisch)", "N": "neutral / flach"},
    "en": {"U": "upwards (bullish)", "D": "downwards (bearish)", "N": "neutral / flat"},
}
_A_TEXT = {
    "de": {"S": "Richtung stimmt mit dem höheren Trend überein.",
           "O": "Richtung läuft gegen den höheren Trend.",
           "U": "Block neutral, höherer Trend zeigt nach oben.",
           "D": "Block neutral, höherer Trend zeigt nach unten.",
           "N": "höherer Trend neutral oder unklar."},
    "en": {"S": "direction is aligned with the higher-timeframe trend.",
           "O": "direction is opposite to the higher-timeframe trend.",
           "U": "no direction in block, higher-timeframe trend up.",
           "D": "no direction in block, higher-timeframe trend down.",
           "N": "higher-timeframe trend neutral or unclear."},
}


def _norm_lang(lang: str | None) -> str:
    l = (lang or "de").lower()
    return l if l in ("de", "en") else "de"


def explain_fomak(fomak: str, lang: str | None = None) -> str:
    """Component-by-component explanation (S/V/P/I/N/D/A each described)."""
    lang = _norm_lang(lang)
    p = parse_fomak(fomak)
    s_bin, v_bin, p_bin, i_bin, n_bin = (int(p[k]) for k in ("S_bin", "V_bin", "P_bin", "I_bin", "N_bin"))
    d_char, a_char = p["D_char"], p["A_char"]

    if lang == "de":
        return (
            f"FOMAK {fomak} beschreibt einen Markt, der insgesamt {_DIR_TEXT['de'][d_char]} gerichtet ist.\n\n"
            f"S (Trendstärke): {s_bin} --> {_S_DESC['de'][s_bin]}\n"
            f"V (Volatilität): {v_bin} --> {_V_DESC['de'][v_bin]}\n"
            f"P (Persistenz):  {p_bin} --> {_P_DESC['de'][p_bin]}\n"
            f"I (Impuls):      {i_bin} --> {_I_DESC['de'][i_bin]}\n"
            f"N (Noise):       {n_bin} --> {_N_DESC['de'][n_bin]}\n"
            f"A (Alignment):   {a_char} --> {_A_TEXT['de'][a_char]}"
        )
    return (
        f"FOMAK {fomak} describes a market that is overall {_DIR_TEXT['en'][d_char]}.\n\n"
        f"S (Trend strength): {s_bin} --> {_S_DESC['en'][s_bin]}\n"
        f"V (Volatility):     {v_bin} --> {_V_DESC['en'][v_bin]}\n"
        f"P (Persistence):    {p_bin} --> {_P_DESC['en'][p_bin]}\n"
        f"I (Impulse):        {i_bin} --> {_I_DESC['en'][i_bin]}\n"
        f"N (Noise):          {n_bin} --> {_N_DESC['en'][n_bin]}\n"
        f"A (Alignment):      {a_char} --> {_A_TEXT['en'][a_char]}"
    )


def interpret_fomak(fomak: str, lang: str | None = None) -> str:
    """Condensed, semantic interpretation — a short readable market description."""
    lang = _norm_lang(lang)
    p = parse_fomak(fomak)
    s_bin, v_bin, p_bin, i_bin, n_bin = (int(p[k]) for k in ("S_bin", "V_bin", "P_bin", "I_bin", "N_bin"))
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

    if lang == "de":
        direction = {"U": "aufwärts", "D": "abwärts", "N": "seitwärts / neutral"}[d_char]
        bias = {"U": "bullisch", "D": "bärisch", "N": "neutral"}[d_char]
        higher_bias = {
            "S": "der höhere Trend unterstützt diese Richtung",
            "O": "der höhere Trend läuft dagegen",
            "U": "Block neutral, höherer Trend aufwärts",
            "D": "Block neutral, höherer Trend abwärts",
            "N": "der höhere Trend ist neutral oder unklar",
        }[a_char]

        if s_bin >= 3 and p_bin >= 2 and n_bin <= 2:
            regime = "einen starken und relativ sauberen Trendmarkt"
        elif s_bin >= 3 and n_bin >= 2:
            regime = "einen starken, aber unruhigen Trend bzw. eine Beschleunigungsphase"
        elif s_bin <= 1 and p_bin <= 1 and n_bin <= 2:
            regime = "einen seitwärts gerichteten Range-Markt"
        elif v_bin >= 3 and n_bin >= 3:
            regime = "eine chaotische, hochvolatile Marktphase"
        else:
            regime = "einen moderat trendigen Markt ohne klaren Extremzustand"

        header = f"Der aktuelle FOMAK {fomak} beschreibt {regime}, der überwiegend {direction} ({bias}) verläuft - {higher_bias}."

        comments = []
        if i_bin >= 3:
            comments.append("Die aktuellen Bewegungen haben ausgeprägten Impuls-Charakter; Breakouts und schnelle Schübe sind wahrscheinlich.")
        elif i_bin <= 1:
            comments.append("Der Impuls ist derzeit schwach - Bewegungen laufen leicht aus.")
        if d_sign != 0 and a_sign != 0 and d_sign != a_sign:
            comments.append("Die aktuelle Bewegung läuft gegen den Trend der höheren Zeitebene - eher eine Korrektur- oder Gegenbewegung.")
        elif d_sign != 0 and a_sign != 0 and d_sign == a_sign:
            comments.append("Kurzfristige und übergeordnete Trendrichtung stimmen überein.")
        return header + ("\n" + " ".join(comments) if comments else "")

    direction = {"U": "upwards", "D": "downwards", "N": "sideways / neutral"}[d_char]
    bias = {"U": "bullish", "D": "bearish", "N": "neutral"}[d_char]
    higher_bias = {
        "S": "the higher timeframe trend supports this direction",
        "O": "the higher timeframe trend points the other way",
        "U": "block neutral, higher timeframe trend up",
        "D": "block neutral, higher timeframe trend down",
        "N": "the higher timeframe trend is neutral or unclear",
    }[a_char]

    if s_bin >= 3 and p_bin >= 2 and n_bin <= 2:
        regime = "a strong and relatively clean trending market"
    elif s_bin >= 3 and n_bin >= 2:
        regime = "a strong but noisy trend or acceleration phase"
    elif s_bin <= 1 and p_bin <= 1 and n_bin <= 2:
        regime = "a sideways, range-bound market"
    elif v_bin >= 3 and n_bin >= 3:
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
