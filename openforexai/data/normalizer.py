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


def price_from_pips(pips_count: float, pair: str) -> Decimal:
    return Decimal(str(pips_count)) * pip_size(pair)


def normalize_price(price: float | Decimal, pair: str) -> float:
    """Return price rounded to the standard decimal places for the pair."""
    p = pip_size(pair)
    decimals = abs(p.as_tuple().exponent)
    return round(float(price), decimals)
