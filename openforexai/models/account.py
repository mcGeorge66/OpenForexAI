from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class AccountStatus(BaseModel):
    """Snapshot of a broker account at a specific point in time.

    All monetary values are in the account's base currency.
    Supported by both OANDA and MT5.
    """

    broker_name: str        # short_name of the broker adapter, e.g. "OANDA_DEMO"
    balance: Decimal        # settled cash balance (closed trade P&L included)
    equity: Decimal         # balance + unrealised P&L of all open positions
    margin: Decimal         # margin currently locked by open positions
    margin_free: Decimal    # equity - margin  (available for new positions)
    leverage: int           # account leverage, e.g. 50 for 1:50
    currency: str           # account currency code, e.g. "USD"
    trade_allowed: bool     # False during news/weekends if broker restricts trading
    margin_level: float | None  # equity / margin * 100; None when no open trades
    recorded_at: datetime   # UTC timestamp when this snapshot was taken
