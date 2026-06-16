from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter

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
from openforexai.utils.logging import get_logger

_log = get_logger(__name__)
_DEFAULT_MT5_API_TIMEOUT_SECONDS = 15.0
_LONG_MT5_CALL_WARN_SECONDS = 2.0


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
        api_timeout_seconds: float = _DEFAULT_MT5_API_TIMEOUT_SECONDS,
        broker_utc_offset_hours: int = 3,
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
        self._api_timeout_seconds = max(float(api_timeout_seconds), 1.0)
        # MT5 reports broker-local time as if it were unix seconds; we relabel as the
        # configured broker timezone instead of leaving it as UTC.
        from datetime import timezone, timedelta
        self._broker_tz = timezone(timedelta(hours=int(broker_utc_offset_hours)))
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
            api_timeout_seconds=cfg.get("api_timeout_seconds", _DEFAULT_MT5_API_TIMEOUT_SECONDS),
            broker_utc_offset_hours=int(cfg.get("broker_utc_offset_hours", 3)),
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

        initialized = await self._call_blocking(
            "initialize",
            mt5.initialize,
            **init_kwargs,
        )
        if not initialized:
            error = mt5.last_error()
            try:
                await self._call_blocking("shutdown", mt5.shutdown)
            except Exception:
                pass
            raise ConnectionError(f"MT5 initialize failed: {error}")
        self._mt5 = mt5

    async def disconnect(self) -> None:
        if self._mt5 is not None:
            await self._call_blocking("shutdown", self._mt5.shutdown)
            self._mt5 = None

    def _mt5_or_raise(self):
        if self._mt5 is None:
            raise RuntimeError("MT5Broker: call connect() first")
        return self._mt5

    def _broker_timestamp(self, raw_timestamp: int | float | None) -> datetime:
        if not raw_timestamp:
            return datetime.now(self._broker_tz)
        # MT5 returns broker-local wall-clock time as if it were unix seconds.
        # We interpret the hour/minute values via UTC then relabel as broker tz
        # so the timestamp carries the correct timezone information.
        return datetime.fromtimestamp(raw_timestamp, tz=UTC).replace(tzinfo=self._broker_tz)

    async def _call_blocking(
        self,
        call_name: str,
        func,
        *args,
        timeout_seconds: float | None = None,
        **kwargs,
    ):
        timeout = self._api_timeout_seconds if timeout_seconds is None else max(float(timeout_seconds), 1.0)
        started = perf_counter()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs),
                timeout=timeout,
            )
        except TimeoutError as exc:
            _log.warning(
                "MT5 call timed out",
                broker=self._short_name,
                call=call_name,
                timeout_seconds=timeout,
            )
            raise TimeoutError(
                f"MT5 call {call_name!r} timed out after {timeout:.1f}s"
            ) from exc

        elapsed = perf_counter() - started
        if elapsed >= _LONG_MT5_CALL_WARN_SECONDS:
            _log.warning(
                "Slow MT5 call detected",
                broker=self._short_name,
                call=call_name,
                latency_ms=round(elapsed * 1000.0, 1),
            )
        return result

    async def _call_mt5(self, call_name: str, *args, **kwargs):
        mt5 = self._mt5_or_raise()
        func = getattr(mt5, call_name)
        return await self._call_blocking(call_name, func, *args, **kwargs)

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
        rates = await self._call_mt5("copy_rates_from_pos", pair, mt5.TIMEFRAME_M5, 0, count)
        if rates is None:
            return []
        rate_fields = set(getattr(getattr(rates, "dtype", None), "names", ()) or ())
        result: list[Candle] = []
        for r in rates:
            spread_raw = r["spread"] if "spread" in rate_fields else 0
            result.append(Candle(
                timestamp=self._broker_timestamp(r["time"]),
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
        info = await self._call_mt5("account_info")
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
        if order.sync_key:
            request["comment"] = order.sync_key

        # STOP_LIMIT needs stoplimit price (the limit portion)
        if order.order_type == OrderType.STOP_LIMIT and order.limit_price:
            request["stoplimit"] = float(order.limit_price)

        result = await self._call_mt5("order_send", request)
        status = (
            TradeStatus.OPEN
            if result.retcode == mt5.TRADE_RETCODE_DONE
            else TradeStatus.REJECTED
        )
        broker_detail = (
            f"retcode={getattr(result, 'retcode', None)}; "
            f"comment={getattr(result, 'comment', '')}"
        )
        return TradeResult(
            order=order,
            broker_order_id=str(result.order),
            broker_name=self._short_name,
            status=status,
            fill_price=Decimal(str(result.price)) if result.price else None,
            opened_at=None,
            close_reason=broker_detail if status == TradeStatus.REJECTED else None,
        )

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_open_positions(self) -> list[Position]:
        positions = await self._call_mt5("positions_get")
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
                opened_at=self._broker_timestamp(p.time),
                sync_key=str(getattr(p, "comment", "")).strip() or None,
            ))
        return result

    async def modify_position(
        self,
        position_id: str,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> TradeResult:
        mt5 = self._mt5_or_raise()
        positions = await self._call_mt5("positions_get", ticket=int(position_id))
        if not positions:
            raise ValueError(f"MT5: position {position_id!r} not found")
        p = positions[0]

        from openforexai.models.trade import TradeSignal
        from openforexai.models.trade import TradeOrder as TO

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": p.symbol,
            "position": p.ticket,
            "sl": float(stop_loss) if stop_loss is not None else float(p.sl or 0.0),
            "tp": float(take_profit) if take_profit is not None else float(p.tp or 0.0),
        }
        result = await self._call_mt5("order_send", request)
        status = (
            TradeStatus.OPEN
            if result.retcode == mt5.TRADE_RETCODE_DONE
            else TradeStatus.REJECTED
        )
        broker_detail = (
            f"retcode={getattr(result, 'retcode', None)}; "
            f"comment={getattr(result, 'comment', '')}"
        )
        dummy_signal = TradeSignal(
            pair=p.symbol,
            direction=TradeDirection.BUY if p.type == 0 else TradeDirection.SELL,
            entry_price=Decimal(str(p.price_open)),
            stop_loss=stop_loss if stop_loss is not None else Decimal(str(p.sl or 0)),
            take_profit=take_profit if take_profit is not None else Decimal(str(p.tp or 0)),
            confidence=0.0,
            reasoning="position modify",
            generated_at=datetime.now(UTC),
            agent_id="supervisor",
        )
        dummy_order = TO(
            signal=dummy_signal,
            units=int(p.volume * 100_000),
            risk_pct=0.0,
            approved_by="supervisor",
        )
        return TradeResult(
            order=dummy_order,
            broker_order_id=position_id,
            broker_name=self._short_name,
            status=status,
            opened_at=datetime.now(UTC),
            close_reason=broker_detail if status == TradeStatus.REJECTED else None,
        )

    async def close_position(self, position_id: str, units: int | None = None, pair: str | None = None) -> TradeResult:
        mt5 = self._mt5_or_raise()
        positions = await self._call_mt5("positions_get", ticket=int(position_id))
        if not positions:
            raise ValueError(f"MT5: position {position_id!r} not found")
        p = positions[0]
        is_buy = p.type == 0
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        current_units = int(p.volume * 100_000)
        close_units = current_units if units is None else int(units)
        if close_units <= 0:
            raise ValueError("units to close must be > 0")
        if close_units > current_units:
            raise ValueError("units to close exceed current position size")
        close_volume = round(close_units / 100_000, 2)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": close_volume,
            "type": close_type,
            "position": p.ticket,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = await self._call_mt5("order_send", request)

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
            units=close_units,
            risk_pct=0.0,
            approved_by="supervisor",
        )
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            status = TradeStatus.CLOSED if close_units == current_units else TradeStatus.OPEN
        else:
            status = TradeStatus.REJECTED
        broker_detail = (
            f"retcode={getattr(result, 'retcode', None)}; "
            f"comment={getattr(result, 'comment', '')}"
        )

        pnl = None
        deal_ticket = getattr(result, "deal", None)
        if deal_ticket:
            deals = await self._call_mt5("history_deals_get", ticket=int(deal_ticket))
            if deals:
                pnl = Decimal(str(getattr(deals[0], "profit", 0)))
        if pnl is None and close_units == current_units:
            pnl = Decimal(str(p.profit))

        return TradeResult(
            order=dummy_order,
            broker_order_id=position_id,
            broker_name=self._short_name,
            status=status,
            fill_price=Decimal(str(result.price)) if result.price else None,
            pnl=pnl,
            closed_at=None,
            close_reason=broker_detail if status == TradeStatus.REJECTED else None,
        )

    async def get_closed_trade_result(
        self,
        position_id: str,
        *,
        pair: str | None = None,
        sync_key: str | None = None,
    ) -> dict[str, object] | None:
        if not position_id:
            return None

        deals = None
        try:
            deals = await self._call_mt5("history_deals_get", position=int(position_id))
        except Exception:
            deals = None

        if not deals:
            date_to = datetime.now(UTC)
            date_from = date_to - timedelta(days=30)
            recent_deals = await self._call_mt5("history_deals_get", date_from, date_to)
            if recent_deals:
                deals = [
                    deal for deal in recent_deals
                    if str(getattr(deal, "position_id", "")) == str(position_id)
                ]

        if not deals:
            return None

        sorted_deals = sorted(
            deals,
            key=lambda deal: int(getattr(deal, "time_msc", 0) or 0) or int(getattr(deal, "time", 0) or 0),
        )
        opened_at = None
        fill_price = None
        first_deal_time = getattr(sorted_deals[0], "time", None) if sorted_deals else None
        if first_deal_time:
            opened_at = self._broker_timestamp(int(first_deal_time))
        # Entry deal (DEAL_ENTRY_IN = 0) carries the fill price
        for deal in sorted_deals:
            if getattr(deal, "entry", None) == 0:
                fp = getattr(deal, "price", None)
                if fp:
                    fill_price = Decimal(str(fp))
                break
        exit_deal = None
        for deal in reversed(sorted_deals):
            entry_flag = getattr(deal, "entry", None)
            if entry_flag in {1, 3}:  # DEAL_ENTRY_OUT / DEAL_ENTRY_OUT_BY
                exit_deal = deal
                break
        if exit_deal is None:
            exit_deal = sorted_deals[-1]

        closed_at = None
        deal_time = getattr(exit_deal, "time", None)
        if deal_time:
            closed_at = self._broker_timestamp(int(deal_time))

        pnl = Decimal(str(getattr(exit_deal, "profit", 0) or 0))
        price = getattr(exit_deal, "price", None)
        reason = getattr(exit_deal, "comment", None) or getattr(exit_deal, "reason", None)
        return {
            "pnl_account_currency": pnl,
            "fill_price": fill_price,
            "close_price": Decimal(str(price)) if price is not None else None,
            "opened_at": opened_at,
            "closed_at": closed_at,
            "close_reason": str(reason) if reason is not None and str(reason).strip() else None,
        }

    async def find_closed_trade_by_sync_key(
        self,
        sync_key: str,
        pair: str | None = None,
    ) -> dict | None:
        if not sync_key:
            return None
        date_to = datetime.now(UTC)
        date_from = date_to - timedelta(days=30)
        try:
            deals = await self._call_mt5("history_deals_get", date_from, date_to)
        except Exception:
            return None
        if not deals:
            return None
        matching = [
            d for d in deals
            if str(getattr(d, "comment", "")).strip() == sync_key
        ]
        if not matching:
            return None
        position_id = str(getattr(matching[0], "position_id", ""))
        if not position_id or position_id == "0":
            return None
        result = await self.get_closed_trade_result(position_id, pair=pair, sync_key=sync_key)
        if result is not None:
            result["broker_order_id"] = position_id
        return result
