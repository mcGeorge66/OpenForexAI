"""Demo broker adapter template.

Purpose:
- Show the minimum structure of a broker adapter.
- Show where config input comes from and what methods must exist.
- Show what values are returned to the system.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from openforexai.models.account import AccountStatus
from openforexai.models.market import Candle
from openforexai.models.trade import (
    OrderType,
    Position,
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)
from openforexai.ports.broker import AbstractBroker


class DemoBrokerAdapter(AbstractBroker):
    """Simple in-memory demo broker.

    This is not production-grade. It demonstrates the adapter contract only.
    """

    def __init__(self, short_name: str, default_pair: str = "EURUSD") -> None:
        self._short_name = short_name
        self._default_pair = default_pair
        self._connected = False

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "DemoBrokerAdapter":
        """Factory used by bootstrap.

        Typical module config fields:
        - short_name (required for stable system identity)
        - default_pair (optional convenience)
        """
        short_name = str(cfg.get("short_name", "")).strip()
        if not short_name:
            raise ValueError("short_name is required in broker config")
        default_pair = str(cfg.get("default_pair", "EURUSD")).upper()
        return cls(short_name=short_name, default_pair=default_pair)

    @property
    def short_name(self) -> str:
        return self._short_name

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def fetch_latest_m5_candle(self, pair: str) -> Candle | None:
        if not self._connected:
            return None
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        base = Decimal("1.1000")
        return Candle(
            timestamp=now,
            open=base,
            high=base + Decimal("0.0008"),
            low=base - Decimal("0.0006"),
            close=base + Decimal("0.0002"),
            tick_volume=100,
            spread=Decimal("0.0002"),
            timeframe="M5",
        )

    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        out: list[Candle] = []
        for i in range(max(1, count)):
            ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            price = Decimal("1.1000") + Decimal(i) * Decimal("0.0001")
            out.append(
                Candle(
                    timestamp=ts,
                    open=price,
                    high=price + Decimal("0.0005"),
                    low=price - Decimal("0.0005"),
                    close=price + Decimal("0.0001"),
                    tick_volume=50 + i,
                    spread=Decimal("0.0002"),
                    timeframe="M5",
                )
            )
        return out

    async def get_account_status(self) -> AccountStatus:
        return AccountStatus(
            broker_name=self.short_name,
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            margin=Decimal("0"),
            margin_free=Decimal("10000"),
            leverage=50,
            currency="USD",
            trade_allowed=True,
            margin_level=None,
            recorded_at=datetime.now(timezone.utc),
        )

    async def place_order(self, order: TradeOrder) -> TradeResult:
        return TradeResult(
            order=order,
            broker_order_id="DEMO-ORDER-1",
            broker_name=self.short_name,
            status=TradeStatus.OPEN,
            fill_price=order.signal.entry_price,
            opened_at=datetime.now(timezone.utc),
        )

    async def close_position(self, position_id: str) -> TradeResult:
        dummy_signal = TradeSignal(
            pair=self._default_pair,
            direction=TradeDirection.BUY,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            confidence=0.5,
            reasoning="demo close_position placeholder",
            generated_at=datetime.now(timezone.utc),
            agent_id="DEMO_ALL..._GA_TEST",
        )
        dummy_order = TradeOrder(
            signal=dummy_signal,
            order_type=OrderType.MARKET,
            units=1000,
            risk_pct=1.0,
            approved_by="DEMO_ALL..._GA_TEST",
        )
        return TradeResult(
            order=dummy_order,
            broker_order_id=position_id,
            broker_name=self.short_name,
            status=TradeStatus.CLOSED,
            fill_price=Decimal("1.1000"),
            pnl=Decimal("0.0"),
            opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc),
        )

    async def get_open_positions(self) -> list[Position]:
        return []

