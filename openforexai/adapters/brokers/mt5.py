from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal

from openforexai.adapters.brokers.base import BrokerBase
from openforexai.models.account import AccountStatus
from openforexai.models.market import Candle
from openforexai.models.trade import (
    OrderType,
    Position,
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeStatus,
)


class MT5Broker(BrokerBase):
    """MetaTrader 5 broker adapter.

    Requirements:
      - Windows only (MetaTrader5 Python package is Windows-exclusive)
      - ``pip install MetaTrader5``

    Supported order types: MARKET, LIMIT, STOP, STOP_LIMIT.
    TRAILING_STOP is not supported natively via the MT5 Python API and will
    raise NotImplementedError.

    Instantiation
    -------------
    ::

        broker = MT5Broker(
            short_name="MT5_PEPPERSTONE",
            account_id=12345678,
            password="secret",
            server="Pepperstone-Demo",
            installation_path="C:/Program Files/MetaTrader 5/terminal64.exe",
        )
        await broker.connect()
        broker.start_background_tasks(pairs, event_bus, repository)
    """

    def __init__(
        self,
        short_name: str,
        account_id: int,
        password: str,
        server: str,
        installation_path: str | None = None,
        monitoring_bus=None,
    ) -> None:
        if not short_name or len(short_name) > 5:
            raise ValueError(
                f"short_name must be 1–5 characters (got {len(short_name)!r}: {short_name!r}). "
                "The first 5 chars are used as the routing ID — keep it short and unique."
            )
        if sys.platform != "win32":
            raise RuntimeError("MT5Broker is only supported on Windows.")
        super().__init__(monitoring_bus=monitoring_bus)
        self._short_name = short_name
        self._account_id = account_id
        self._password = password
        self._server = server
        self._installation_path = installation_path
        self._mt5 = None  # set in connect()

    @classmethod
    def from_config(cls, cfg: dict) -> MT5Broker:
        short_name = str(cfg.get("short_name", "")).strip()
        if not short_name:
            raise ValueError(
                "Missing 'short_name' in broker config. "
                "Set a unique short_name (1-5 chars)."
            )
        account_id_raw = cfg.get("account_id", 0)
        return cls(
            short_name=short_name,
            account_id=int(account_id_raw),
            password=cfg.get("password", ""),
            server=cfg.get("server", ""),
            installation_path=cfg.get("installation_path", None),
        )

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    def short_name(self) -> str:
        return self._short_name

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        import MetaTrader5 as mt5  # type: ignore[import]

        init_kwargs: dict[str, str | int] = {
            "login": self._account_id,
            "password": self._password,
            "server": self._server,
        }
        if isinstance(self._installation_path, str) and self._installation_path.strip():
            init_kwargs["path"] = self._installation_path.strip()

        if not mt5.initialize(**init_kwargs):
            raise ConnectionError(f"MT5 initialize failed: {mt5.last_error()}")
        self._mt5 = mt5

    async def disconnect(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None

    def _mt5_or_raise(self):
        if self._mt5 is None:
            raise RuntimeError("MT5Broker: call connect() first")
        return self._mt5

    # ── Market data ───────────────────────────────────────────────────────────

    async def fetch_latest_m5_candle(self, pair: str) -> Candle | None:
        """Return the most recently completed M5 candle."""
        candles = await self.get_historical_m5_candles(pair, count=2)
        if not candles:
            return None
        return candles[-1]

    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        """Fetch up to *count* historical M5 candles (oldest first)."""
        mt5 = self._mt5_or_raise()
        rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M5, 0, count)
        if rates is None:
            return []
        rate_fields = set(getattr(getattr(rates, "dtype", None), "names", ()) or ())
        result: list[Candle] = []
        for r in rates:
            spread_raw = r["spread"] if "spread" in rate_fields else 0
            result.append(Candle(
                timestamp=datetime.fromtimestamp(r["time"], tz=UTC),
                open=Decimal(str(r["open"])),
                high=Decimal(str(r["high"])),
                low=Decimal(str(r["low"])),
                close=Decimal(str(r["close"])),
                tick_volume=int(r["tick_volume"]),
                spread=Decimal(str(spread_raw)),
                timeframe="M5",
            ))
        return result

    # ── Account ───────────────────────────────────────────────────────────────

    async def get_account_status(self) -> AccountStatus:
        mt5 = self._mt5_or_raise()
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("MT5: account_info() returned None")
        margin = Decimal(str(info.margin))
        equity = Decimal(str(info.equity))
        margin_level = (
            float(equity / margin * 100) if margin and margin > 0 else None
        )
        return AccountStatus(
            broker_name=self._short_name,
            balance=Decimal(str(info.balance)),
            equity=equity,
            margin=margin,
            margin_free=Decimal(str(info.margin_free)),
            leverage=int(info.leverage),
            currency=info.currency,
            trade_allowed=info.trade_allowed,
            margin_level=margin_level,
            recorded_at=datetime.now(UTC),
        )

    # ── Orders ────────────────────────────────────────────────────────────────

    async def place_order(self, order: TradeOrder) -> TradeResult:
        mt5 = self._mt5_or_raise()
        signal = order.signal

        if order.order_type == OrderType.TRAILING_STOP:
            raise NotImplementedError(
                "TRAILING_STOP is not supported by the MT5 Python adapter."
            )

        action_map = {
            OrderType.MARKET: mt5.TRADE_ACTION_DEAL,
            OrderType.LIMIT: mt5.TRADE_ACTION_PENDING,
            OrderType.STOP: mt5.TRADE_ACTION_PENDING,
            OrderType.STOP_LIMIT: mt5.TRADE_ACTION_PENDING,
        }
        type_map_buy = {
            OrderType.MARKET: mt5.ORDER_TYPE_BUY,
            OrderType.LIMIT: mt5.ORDER_TYPE_BUY_LIMIT,
            OrderType.STOP: mt5.ORDER_TYPE_BUY_STOP,
            OrderType.STOP_LIMIT: mt5.ORDER_TYPE_BUY_STOP_LIMIT,
        }
        type_map_sell = {
            OrderType.MARKET: mt5.ORDER_TYPE_SELL,
            OrderType.LIMIT: mt5.ORDER_TYPE_SELL_LIMIT,
            OrderType.STOP: mt5.ORDER_TYPE_SELL_STOP,
            OrderType.STOP_LIMIT: mt5.ORDER_TYPE_SELL_STOP_LIMIT,
        }
        is_buy = signal.direction == TradeDirection.BUY
        order_type = (type_map_buy if is_buy else type_map_sell)[order.order_type]
        action = action_map[order.order_type]

        # Price for pending orders
        if order.order_type == OrderType.MARKET:
            price = 0.0
        elif order.order_type in (OrderType.LIMIT, OrderType.STOP):
            price = float(order.limit_price or order.stop_price or signal.entry_price)
        else:  # STOP_LIMIT
            price = float(order.stop_price or signal.entry_price)

        request: dict = {
            "action": action,
            "symbol": signal.pair,
            "volume": round(order.units / 100_000, 2),
            "type": order_type,
            "price": price,
            "sl": float(signal.stop_loss) if signal.stop_loss else 0.0,
            "tp": float(signal.take_profit) if signal.take_profit else 0.0,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # STOP_LIMIT needs stoplimit price (the limit portion)
        if order.order_type == OrderType.STOP_LIMIT and order.limit_price:
            request["stoplimit"] = float(order.limit_price)

        result = mt5.order_send(request)
        status = (
            TradeStatus.OPEN
            if result.retcode == mt5.TRADE_RETCODE_DONE
            else TradeStatus.REJECTED
        )
        return TradeResult(
            order=order,
            broker_order_id=str(result.order),
            broker_name=self._short_name,
            status=status,
            fill_price=Decimal(str(result.price)) if result.price else None,
            opened_at=datetime.now(UTC),
        )

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_open_positions(self) -> list[Position]:
        mt5 = self._mt5_or_raise()
        positions = mt5.positions_get()
        if not positions:
            return []
        result: list[Position] = []
        for p in positions:
            direction = TradeDirection.BUY if p.type == 0 else TradeDirection.SELL
            result.append(Position(
                broker_position_id=str(p.ticket),
                broker_name=self._short_name,
                pair=p.symbol,
                direction=direction,
                units=int(p.volume * 100_000),
                open_price=Decimal(str(p.price_open)),
                current_price=Decimal(str(p.price_current)),
                stop_loss=Decimal(str(p.sl)) if p.sl else None,
                take_profit=Decimal(str(p.tp)) if p.tp else None,
                unrealized_pnl=Decimal(str(p.profit)),
                opened_at=datetime.fromtimestamp(p.time, tz=UTC),
            ))
        return result

    async def close_position(self, position_id: str) -> TradeResult:
        mt5 = self._mt5_or_raise()
        positions = mt5.positions_get(ticket=int(position_id))
        if not positions:
            raise ValueError(f"MT5: position {position_id!r} not found")
        p = positions[0]
        is_buy = p.type == 0
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "position": p.ticket,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)

        from openforexai.models.trade import TradeDirection, TradeSignal
        from openforexai.models.trade import TradeOrder as TO
        dummy_signal = TradeSignal(
            pair=p.symbol,
            direction=TradeDirection.BUY if is_buy else TradeDirection.SELL,
            entry_price=Decimal(str(p.price_open)),
            stop_loss=Decimal("0"),
            take_profit=Decimal("0"),
            confidence=0.0,
            reasoning="position close",
            generated_at=datetime.now(UTC),
            agent_id="supervisor",
        )
        dummy_order = TO(
            signal=dummy_signal,
            units=int(p.volume * 100_000),
            risk_pct=0.0,
            approved_by="supervisor",
        )
        status = (
            TradeStatus.CLOSED
            if result.retcode == mt5.TRADE_RETCODE_DONE
            else TradeStatus.REJECTED
        )
        return TradeResult(
            order=dummy_order,
            broker_order_id=position_id,
            broker_name=self._short_name,
            status=status,
            fill_price=Decimal(str(result.price)) if result.price else None,
            closed_at=datetime.now(UTC),
        )
