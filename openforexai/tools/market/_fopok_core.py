"""FOPOK core — the position counterpart to the FOMAK.

The FOMAK describes how the market *moves*: strength, direction, volatility,
persistence, impulse, higher-timeframe alignment. It says nothing about *where*
price stands, and a trader decides largely on that: how far is the next barrier,
how worn is it, and is there room for a target at all.

FOPOK = {Position}{Width}{BarrierAbove}{BarrierBelow}{HigherTimeframe}

    Position       D own  / M iddle / U p      — where in the corridor
    Width          T ight / N ormal / W ide    — corridor width in ATR
    BarrierAbove   F resh / E xhausted         — how often it has been tested
    BarrierBelow   F resh / E xhausted
    Higher TF      A ligned / N one / C onflict

Letters, not digits, on purpose: the codes and their explanations are what the
memory search compares, and a text embedding reads "Up" as meaning while "3"
carries none. Measured on the real model: changing a number in a sentence moves
the similarity score by 0.04, changing its meaning by 0.27.

Every letter is unique across the five positions, so a code can be read without
knowing which position a letter came from.

The width thresholds are calibrated the same way the FOMAK's bin edges are:
percentiles of real windows, not judgement. The touch count and the
higher-timeframe tolerance are not — they are still chosen, and marked as such
where they are defined.
"""
from __future__ import annotations

from typing import Any

# Corridor width in ATR: below TIGHT it is tight, above WIDE it is wide.
# From the 33rd/66th percentiles of 2210 real M15 windows across both pairs
# (13.07.-16.09.2026), the same way the FOMAK's bin edges were derived. The
# first guess here was 3.0/8.0, which was wrong by a factor of five: the whole
# corridor is a median 0.70 ATR wide, so everything came out Tight.
WIDTH_TIGHT_ATR = 0.56
WIDTH_WIDE_ATR = 0.88
# A level merged from this many swings has been tested repeatedly without
# holding or breaking — get_swing_levels' own docs call that weaker, not
# stronger, so it reads as "exhausted".
BARRIER_EXHAUSTED_TOUCHES = 3
# A higher-timeframe level this close to ours (in ATR) counts as confirming it.
HIGHER_CONFIRM_ATR = 1.0


class FopokInputError(ValueError):
    """Raised when the level structure is too incomplete to place price in it."""


def _third(fraction: float) -> str:
    if fraction < 1 / 3:
        return "D"
    if fraction > 2 / 3:
        return "U"
    return "M"


def _width_char(width_atr: float) -> str:
    if width_atr < WIDTH_TIGHT_ATR:
        return "T"
    if width_atr > WIDTH_WIDE_ATR:
        return "W"
    return "N"


def _barrier_char(level: dict[str, Any] | None) -> str:
    if not isinstance(level, dict):
        return "F"
    try:
        touches = int(level.get("touch_count") or 1)
    except (TypeError, ValueError):
        touches = 1
    return "E" if touches >= BARRIER_EXHAUSTED_TOUCHES else "F"


def _higher_char(
    *,
    resistance: float,
    support: float,
    atr: float,
    higher_position: str | None,
    own_position: str,
    higher_levels: list[float],
) -> str:
    """Aligned, no opinion, or in conflict.

    Conflict is the strong statement and is checked first: price sitting at the
    top of this corridor while sitting at the bottom of the higher-timeframe one
    means the two disagree about where there is room.
    """
    if higher_position and {own_position, higher_position} == {"U", "D"}:
        return "C"
    tolerance = atr * HIGHER_CONFIRM_ATR
    for level in higher_levels:
        if abs(level - resistance) <= tolerance or abs(level - support) <= tolerance:
            return "A"
    return "N"


def compute_fopok(
    *,
    current_price: float,
    nearest_resistance: dict[str, Any] | None,
    nearest_support: dict[str, Any] | None,
    atr: float,
    higher_resistance: dict[str, Any] | None = None,
    higher_support: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One FOPOK for the level structure around *current_price*.

    Expects the shape get_swing_levels returns, so the clustering, touch_count
    and ATR are reused rather than re-implemented.
    """
    if not isinstance(nearest_resistance, dict) or not isinstance(nearest_support, dict):
        raise FopokInputError(
            "Need a nearest resistance and a nearest support to place price in a corridor."
        )
    if not atr or atr <= 0:
        raise FopokInputError("Need a positive ATR to express distances in ATR units.")

    res = float(nearest_resistance["price"])
    sup = float(nearest_support["price"])
    corridor = res - sup
    if corridor <= 0:
        raise FopokInputError("Resistance is not above support — level structure is inconsistent.")

    fraction = (float(current_price) - sup) / corridor
    position = _third(fraction)
    width_atr = corridor / atr
    room_up_atr = (res - float(current_price)) / atr
    room_down_atr = (float(current_price) - sup) / atr

    higher_levels = [
        float(lv["price"])
        for lv in (higher_resistance, higher_support)
        if isinstance(lv, dict) and lv.get("price") is not None
    ]
    higher_position = None
    if isinstance(higher_resistance, dict) and isinstance(higher_support, dict):
        h_res, h_sup = float(higher_resistance["price"]), float(higher_support["price"])
        if h_res > h_sup:
            higher_position = _third((float(current_price) - h_sup) / (h_res - h_sup))

    fopok = "".join([
        position,
        _width_char(width_atr),
        _barrier_char(nearest_resistance),
        _barrier_char(nearest_support),
        _higher_char(
            resistance=res, support=sup, atr=atr,
            higher_position=higher_position, own_position=position,
            higher_levels=higher_levels,
        ),
    ])
    return {
        "fopok": fopok,
        "position": position,
        "raw_values": {
            "corridor_pips_in_atr": round(width_atr, 2),
            "position_in_corridor": round(fraction, 3),
            "room_up_atr": round(room_up_atr, 2),
            "room_down_atr": round(room_down_atr, 2),
            "resistance": res,
            "support": sup,
            "resistance_touches": nearest_resistance.get("touch_count"),
            "support_touches": nearest_support.get("touch_count"),
            "atr": atr,
            "higher_position": higher_position,
        },
    }


_POSITION_TEXT = {
    "D": "near the lower edge of its corridor, close to support",
    "M": "in the middle of its corridor",
    "U": "near the upper edge of its corridor, close to resistance",
}
_WIDTH_TEXT = {
    "T": "a tight corridor with little room in either direction",
    "N": "a corridor of normal width",
    "W": "a wide corridor with room on both sides",
}
_BARRIER_TEXT = {"F": "fresh, barely tested", "E": "exhausted, tested repeatedly"}
_HIGHER_TEXT = {
    "A": "the higher timeframe confirms this level structure",
    "N": "the higher timeframe has no level of its own nearby",
    "C": "the higher timeframe disagrees about where the room is",
}


def explain_fopok(fopok: str, raw: dict[str, Any] | None = None) -> str:
    """Plain words, because words are what the memory search compares."""
    if len(fopok) != 5:
        raise FopokInputError(f"A FOPOK has five characters, got {fopok!r}")
    pos, width, above, below, higher = fopok
    for char, table in ((pos, _POSITION_TEXT), (width, _WIDTH_TEXT),
                        (above, _BARRIER_TEXT), (below, _BARRIER_TEXT),
                        (higher, _HIGHER_TEXT)):
        if char not in table:
            raise FopokInputError(f"Unknown character {char!r} in FOPOK {fopok!r}")

    lines = [
        f"FOPOK {fopok}: price is {_POSITION_TEXT[pos]}, in {_WIDTH_TEXT[width]}.",
        f"The barrier above is {_BARRIER_TEXT[above]}; the barrier below is {_BARRIER_TEXT[below]}.",
        f"On the wider view, {_HIGHER_TEXT[higher]}.",
    ]
    if raw:
        up, down = raw.get("room_up_atr"), raw.get("room_down_atr")
        if up is not None and down is not None:
            lines.append(
                f"Room to the barrier above is {up} ATR, to the one below {down} ATR — "
                "a target beyond either of those needs the barrier to break first."
            )
    return "\n".join(lines)
