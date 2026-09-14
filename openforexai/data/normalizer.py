from __future__ import annotations

from decimal import Decimal

# Pip sizes per instrument (most majors are 4dp; JPY pairs are 2dp)
_PIP_SIZES: dict[str, Decimal] = {
    "EURUSD": Decimal("0.0001"),
    "GBPUSD": Decimal("0.0001"),
    "AUDUSD": Decimal("0.0001"),
    "NZDUSD": Decimal("0.0001"),
    "USDCAD": Decimal("0.0001"),
    "USDCHF": Decimal("0.0001"),
    "USDJPY": Decimal("0.01"),
    "EURJPY": Decimal("0.01"),
    "GBPJPY": Decimal("0.01"),
    "CADJPY": Decimal("0.01"),
}

_DEFAULT_PIP = Decimal("0.0001")


def pip_size(pair: str) -> Decimal:
    return _PIP_SIZES.get(pair.upper(), _DEFAULT_PIP)


def pips(price_delta: Decimal, pair: str) -> float:
    """Convert a raw price difference to pips."""
    return float(abs(price_delta) / pip_size(pair))


def pnl_in_pips(
    pair: str,
    direction: str,
    entry_price: Decimal | None,
    exit_price: Decimal | None,
) -> Decimal | None:
    """Realised result in pips, signed: negative means a loss.

    Deliberately not built on :func:`pips`, which takes the absolute value —
    for a result the sign is the whole point. A short earns when the exit is
    below the entry, so the raw difference is inverted for SELL.

    Returns None when a price is missing rather than guessing, so a trade
    without a recorded fill stays empty instead of showing a wrong number.
    """
    if entry_price is None or exit_price is None:
        return None
    delta = Decimal(str(exit_price)) - Decimal(str(entry_price))
    if str(direction).upper() == "SELL":
        delta = -delta
    return (delta / pip_size(pair)).quantize(Decimal("0.1"))


def price_from_pips(pips_count: float, pair: str) -> Decimal:
    return Decimal(str(pips_count)) * pip_size(pair)


def normalize_price(price: float | Decimal, pair: str) -> float:
    """Return price rounded to the standard decimal places for the pair."""
    p = pip_size(pair)
    decimals = abs(p.as_tuple().exponent)
    return round(float(price), decimals)

