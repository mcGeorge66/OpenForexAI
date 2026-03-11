from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from openforexai.adapters.brokers.base import BrokerBase, normalize_candle, retry_async
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

# OANDA v20 API hard limit for candles per request
_OANDA_MAX_CANDLES = 5000

# OANDA granularity codes for M5 only (higher TFs derived by DataContainer)
_TF_MAP = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D": "D",
}


def _instrument(pair: str) -> str:
    """Convert 'EURUSD' → 'EUR_USD' for OANDA API."""
    if "_" in pair:
        return pair
    if "/" in pair:
        return pair.replace("/", "_")
    return pair[:3] + "_" + pair[3:]


def _pair(instrument: str) -> str:
    """Convert 'EUR_USD' → 'EURUSD' for internal use."""
    return instrument.replace("_", "")


class OANDABroker(BrokerBase):
    """OANDA v20 REST adapter.

    Implements the full AbstractBroker contract.  Streaming (tick-level) is
    intentionally removed — the system operates on M5 candles only.

    Supported order types: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP.

    Instantiation
    -------------
    ::

        broker = OANDABroker(
            short_name="OANDA_DEMO",
            api_key="...",
            account_id="...",
            practice=True,
        )
        await broker.connect()
        broker.start_background_tasks(pairs, event_bus, repository)

    When *api_url* is supplied it overrides the practice/live URL selection.
    The value may include or omit a trailing ``/v3`` segment — it is stripped
    automatically because every request path already begins with ``/v3/``.
    """

    def __init__(
        self,
        short_name: str,
        api_key: str,
        account_id: str,
        api_url: str,
        practice: bool = True,
        monitoring_bus=None,
    ) -> None:
        if not short_name or len(short_name) > 5:
            raise ValueError(
                f"short_name must be 1–5 characters (got {len(short_name)!r}: {short_name!r}). "
                "The first 5 chars are used as the routing ID — keep it short and unique."
            )
        if not api_url:
            raise ValueError(
                "api_url is required — set it in the broker module config. "
                "Practice: https://api-fxpractice.oanda.com/v3  "
                "Live:     https://api-fxtrade.oanda.com/v3"
            )
        super().__init__(monitoring_bus=monitoring_bus)
        self._short_name = short_name
        self._api_key = api_key
        self._account_id = account_id
        self._practice = practice

        # Strip trailing /v3 — internal paths already begin with /v3/
        base = api_url.rstrip("/")
        self._base_url = base[:-3] if base.endswith("/v3") else base

        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_config(cls, cfg: dict) -> OANDABroker:
        api_url = cfg.get("api_url", "")
        if not api_url:
            raise ValueError(
                "Missing 'api_url' in broker config. "
                "Practice: https://api-fxpractice.oanda.com/v3  "
                "Live:     https://api-fxtrade.oanda.com/v3"
            )
        return cls(
            short_name=cfg.get("short_name", "OANDA"),
            api_key=cfg.get("api_key", ""),
            account_id=cfg.get("account_id", ""),
            api_url=api_url,
            practice=cfg.get("practice", True),
        )

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    def short_name(self) -> str:
        return self._short_name

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OANDABroker: call connect() first")
        return self._client

    # ── Market data ───────────────────────────────────────────────────────────

    async def fetch_latest_m5_candle(self, pair: str) -> Candle | None:
        """Fetch the most recently completed M5 candle from OANDA."""
        candles = await self.get_historical_m5_candles(pair, count=2)
        if not candles:
            return None
        return candles[-1]

    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        """Fetch up to *count* completed M5 candles (oldest first).

        Paginates automatically when *count* exceeds OANDA's 5000-candle limit.
        """
        if count <= _OANDA_MAX_CANDLES:
            return await self._fetch_m5_chunk(pair, count=count, from_time=None)

        # Paginate: estimate start time and walk forward in 5000-candle pages.
        # M5 bars are 5 min each; forex is ~5/7 days, so use a 1.6× time buffer
        # to account for weekends and bank holidays.
        now = datetime.now(UTC)
        from_time = now - timedelta(minutes=int(count * 5 * 1.6))

        all_candles: list[Candle] = []
        while len(all_candles) < count:
            chunk = await self._fetch_m5_chunk(
                pair, count=_OANDA_MAX_CANDLES, from_time=from_time
            )
            if not chunk:
                break
            all_candles.extend(chunk)
            if len(chunk) < _OANDA_MAX_CANDLES:
                break  # reached present; no more pages
            from_time = chunk[-1].timestamp + timedelta(minutes=1)

        # Return at most *count* candles, oldest first
        return all_candles[-count:] if len(all_candles) > count else all_candles

    async def _fetch_m5_chunk(
        self,
        pair: str,
        count: int,
        from_time: datetime | None,
    ) -> list[Candle]:
        """Single OANDA candle request (≤ 5000 bars).  Returns candles oldest-first."""
        client = self._c()
        instrument = _instrument(pair)
        params: dict = {"granularity": "M5", "count": count, "price": "BA"}
        if from_time is not None:
            params["from"] = from_time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        resp = await retry_async(
            lambda: client.get(
                f"/v3/instruments/{instrument}/candles",
                params=params,
            ),
            attempts=3,
        )
        resp.raise_for_status()
        raw_candles = resp.json().get("candles", [])
        result: list[Candle] = []
        for c in raw_candles:
            if not c.get("complete", True):
                continue  # skip the still-forming candle
            bid = c.get("bid", {})
            ask = c.get("ask", {})
            bid_close = Decimal(bid.get("c", "0"))
            ask_close = Decimal(ask.get("c", "0"))
            spread_pips = ask_close - bid_close

            result.append(normalize_candle(
                {
                    "time": c["time"],
                    "open": bid.get("o", "0"),
                    "high": bid.get("h", "0"),
                    "low": bid.get("l", "0"),
                    "close": bid.get("c", "0"),
                    "tick_volume": c.get("volume", 0),
                    "spread": str(spread_pips),
                },
                pair,
                "M5",
            ))
        return result

    # ── Account ───────────────────────────────────────────────────────────────

    async def get_account_status(self) -> AccountStatus:
        client = self._c()
        resp = await retry_async(
            lambda: client.get(f"/v3/accounts/{self._account_id}/summary"),
            attempts=3,
        )
        resp.raise_for_status()
        acct = resp.json()["account"]
        margin = Decimal(str(acct.get("marginUsed", "0")))
        equity = Decimal(str(acct.get("NAV", acct.get("balance", "0"))))
        margin_level = (
            float(equity / margin * 100) if margin and margin > 0 else None
        )
        return AccountStatus(
            broker_name=self._short_name,
            balance=Decimal(str(acct["balance"])),
            equity=equity,
            margin=margin,
            margin_free=Decimal(str(acct.get("marginAvailable", "0"))),
            leverage=int(acct.get("marginRate", 0.02) and round(1 / float(acct.get("marginRate", 0.02)))),
            currency=acct.get("currency", "USD"),
            trade_allowed=not acct.get("tradingDisabled", False),
            margin_level=margin_level,
            recorded_at=datetime.now(UTC),
        )

    # ── Orders ────────────────────────────────────────────────────────────────

    async def place_order(self, order: TradeOrder) -> TradeResult:
        client = self._c()
        signal = order.signal
        instrument = _instrument(signal.pair)
        units = order.units if signal.direction == TradeDirection.BUY else -order.units

        order_body: dict = {
            "instrument": instrument,
            "units": str(units),
        }

        # ── Common SL/TP ─────────────────────────────────────────────────────
        if signal.stop_loss:
            order_body["stopLossOnFill"] = {"price": str(signal.stop_loss)}
        if signal.take_profit:
            order_body["takeProfitOnFill"] = {"price": str(signal.take_profit)}

        # ── Trailing stop ─────────────────────────────────────────────────────
        if order.trailing_stop_distance:
            order_body["trailingStopLossOnFill"] = {
                "distance": str(order.trailing_stop_distance)
            }

        # ── Order-type specific fields ────────────────────────────────────────
        if order.order_type == OrderType.MARKET:
            order_body["type"] = "MARKET"

        elif order.order_type == OrderType.LIMIT:
            if not order.limit_price:
                raise ValueError("LIMIT order requires limit_price")
            order_body["type"] = "LIMIT"
            order_body["price"] = str(order.limit_price)

        elif order.order_type == OrderType.STOP:
            if not order.stop_price:
                raise ValueError("STOP order requires stop_price")
            order_body["type"] = "STOP"
            order_body["price"] = str(order.stop_price)

        elif order.order_type == OrderType.STOP_LIMIT:
            if not order.stop_price or not order.limit_price:
                raise ValueError("STOP_LIMIT order requires both stop_price and limit_price")
            # OANDA implements this as a STOP order with priceBound
            order_body["type"] = "STOP"
            order_body["price"] = str(order.stop_price)
            order_body["priceBound"] = str(order.limit_price)

        elif order.order_type == OrderType.TRAILING_STOP:
            if not order.trailing_stop_distance:
                raise ValueError("TRAILING_STOP order requires trailing_stop_distance")
            order_body["type"] = "MARKET"
            # Trailing stop is set via trailingStopLossOnFill above

        else:
            raise NotImplementedError(f"Order type not supported: {order.order_type}")

        resp = await retry_async(
            lambda: client.post(
                f"/v3/accounts/{self._account_id}/orders",
                content=json.dumps({"order": order_body}),
            ),
            attempts=3,
        )
        resp.raise_for_status()
        data = resp.json()
        fill = data.get("orderFillTransaction", {})

        return TradeResult(
            order=order,
            broker_order_id=fill.get("orderID", data.get("relatedTransactionIDs", [""])[0]),
            broker_name=self._short_name,
            status=TradeStatus.OPEN if fill else TradeStatus.PENDING,
            fill_price=Decimal(fill["price"]) if fill.get("price") else None,
            opened_at=datetime.now(UTC),
        )

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_open_positions(self) -> list[Position]:
        client = self._c()
        resp = await retry_async(
            lambda: client.get(f"/v3/accounts/{self._account_id}/openTrades"),
            attempts=3,
        )
        resp.raise_for_status()
        positions: list[Position] = []
        for t in resp.json().get("trades", []):
            direction = TradeDirection.BUY if int(t["currentUnits"]) > 0 else TradeDirection.SELL
            sl = t.get("stopLossOrder", {}).get("price")
            tp = t.get("takeProfitOrder", {}).get("price")
            positions.append(Position(
                broker_position_id=t["id"],
                broker_name=self._short_name,
                pair=_pair(t["instrument"]),
                direction=direction,
                units=abs(int(t["currentUnits"])),
                open_price=Decimal(t["price"]),
                current_price=Decimal(t.get("price", t["price"])),
                stop_loss=Decimal(sl) if sl else None,
                take_profit=Decimal(tp) if tp else None,
                unrealized_pnl=Decimal(t.get("unrealizedPL", "0")),
                opened_at=datetime.fromisoformat(t["openTime"].replace("Z", "+00:00")),
            ))
        return positions

    async def close_position(self, position_id: str) -> TradeResult:
        client = self._c()
        resp = await retry_async(
            lambda: client.put(
                f"/v3/accounts/{self._account_id}/trades/{position_id}/close"
            ),
            attempts=3,
        )
        resp.raise_for_status()
        data = resp.json().get("orderFillTransaction", {})

        # Minimal dummy order needed to satisfy TradeResult schema
        from openforexai.models.trade import TradeDirection, TradeOrder, TradeSignal
        dummy_signal = TradeSignal(
            pair="",
            direction=TradeDirection.BUY,
            entry_price=Decimal("0"),
            stop_loss=Decimal("0"),
            take_profit=Decimal("0"),
            confidence=0.0,
            reasoning="position close",
            generated_at=datetime.now(UTC),
            agent_id="supervisor",
        )
        dummy_order = TradeOrder(
            signal=dummy_signal,
            units=0,
            risk_pct=0.0,
            approved_by="supervisor",
        )
        return TradeResult(
            order=dummy_order,
            broker_order_id=position_id,
            broker_name=self._short_name,
            status=TradeStatus.CLOSED,
            fill_price=Decimal(data["price"]) if data.get("price") else None,
            pnl=Decimal(data.get("pl", "0")),
            closed_at=datetime.now(UTC),
        )

