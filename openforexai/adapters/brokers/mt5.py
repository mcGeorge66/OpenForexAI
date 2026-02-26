from __future__ import annotations

import sys
from decimal import Decimal
from typing import AsyncIterator

from openforexai.models.market import Candle, Tick
from openforexai.models.trade import Position, TradeOrder, TradeResult, TradeStatus
from openforexai.ports.broker import AbstractBroker


class MT5Broker(AbstractBroker):
    """MetaTrader 5 broker adapter (Windows only)."""

    def __init__(self, login: int, password: str, server: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("MT5Broker is only supported on Windows.")
        self._login = login
        self._password = password
        self._server = server
        self._mt5: object | None = None

    async def connect(self) -> None:
        import MetaTrader5 as mt5  # type: ignore[import]

        if not mt5.initialize(login=self._login, password=self._password, server=self._server):
            raise ConnectionError(f"MT5 initialize failed: {mt5.last_error()}")
        self._mt5 = mt5

    async def disconnect(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()  # type: ignore[union-attr]

    async def get_account_balance(self) -> float:
        info = self._mt5.account_info()  # type: ignore[union-attr]
        return float(info.balance)

    async def get_historical_candles(
        self, pair: str, timeframe: str, count: int
    ) -> list[Candle]:
        import MetaTrader5 as mt5
        from datetime import datetime, timezone

        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        rates = mt5.copy_rates_from_pos(pair, tf_map[timeframe], 0, count)
        if rates is None:
            return []
        return [
            Candle(
                timestamp=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                open=Decimal(str(r["open"])),
                high=Decimal(str(r["high"])),
                low=Decimal(str(r["low"])),
                close=Decimal(str(r["close"])),
                volume=int(r["tick_volume"]),
                timeframe=timeframe,
            )
            for r in rates
        ]

    async def get_open_positions(self) -> list[Position]:
        from datetime import datetime, timezone

        from openforexai.models.trade import TradeDirection

        positions = self._mt5.positions_get()  # type: ignore[union-attr]
        if not positions:
            return []
        result: list[Position] = []
        for p in positions:
            direction = TradeDirection.BUY if p.type == 0 else TradeDirection.SELL
            result.append(
                Position(
                    broker_position_id=str(p.ticket),
                    pair=p.symbol,
                    direction=direction,
                    units=int(p.volume * 100_000),
                    open_price=Decimal(str(p.price_open)),
                    current_price=Decimal(str(p.price_current)),
                    unrealized_pnl=Decimal(str(p.profit)),
                    opened_at=datetime.fromtimestamp(p.time, tz=timezone.utc),
                )
            )
        return result

    async def place_order(self, order: TradeOrder) -> TradeResult:
        import MetaTrader5 as mt5
        from datetime import datetime, timezone

        signal = order.signal
        action = mt5.ORDER_TYPE_BUY if signal.direction.value == "BUY" else mt5.ORDER_TYPE_SELL
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": signal.pair,
            "volume": round(order.units / 100_000, 2),
            "type": action,
            "sl": float(signal.stop_loss),
            "tp": float(signal.take_profit),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        status = TradeStatus.OPEN if result.retcode == mt5.TRADE_RETCODE_DONE else TradeStatus.REJECTED
        return TradeResult(
            order=order,
            broker_order_id=str(result.order),
            status=status,
            fill_price=Decimal(str(result.price)) if result.price else None,
            opened_at=datetime.now(timezone.utc),
        )

    async def close_position(self, position_id: str) -> TradeResult:
        raise NotImplementedError("MT5 close_position not yet implemented.")

    async def stream_ticks(self, pairs: list[str]) -> AsyncIterator[Tick]:
        raise NotImplementedError("MT5 tick streaming not yet implemented.")
