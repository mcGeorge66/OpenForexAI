from __future__ import annotations

import json
from decimal import Decimal
from typing import AsyncIterator

import httpx

from openforexai.adapters.brokers.base import normalize_candle, retry_async
from openforexai.models.market import Candle, Tick
from openforexai.models.trade import (
    Position,
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeStatus,
)
from openforexai.ports.broker import AbstractBroker

_PRACTICE_URL = "https://api-fxpractice.oanda.com"
_LIVE_URL = "https://api-fxtrade.oanda.com"
_STREAM_PRACTICE = "https://stream-fxpractice.oanda.com"
_STREAM_LIVE = "https://stream-fxtrade.oanda.com"

_TF_MAP = {
    "M1": "M1", "M5": "M5", "H1": "H1", "H4": "H4", "D1": "D"
}


class OANDABroker(AbstractBroker):
    """OANDA v20 REST + Streaming adapter."""

    def __init__(self, api_key: str, account_id: str, practice: bool = True) -> None:
        self._api_key = api_key
        self._account_id = account_id
        self._base_url = _PRACTICE_URL if practice else _LIVE_URL
        self._stream_url = _STREAM_PRACTICE if practice else _STREAM_LIVE
        self._client: httpx.AsyncClient | None = None

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

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OANDABroker: call connect() first")
        return self._client

    async def get_account_balance(self) -> float:
        client = self._client_or_raise()
        resp = await retry_async(
            lambda: client.get(f"/v3/accounts/{self._account_id}/summary"), attempts=3
        )
        resp.raise_for_status()
        return float(resp.json()["account"]["balance"])

    async def get_historical_candles(
        self, pair: str, timeframe: str, count: int
    ) -> list[Candle]:
        client = self._client_or_raise()
        instrument = pair.replace("/", "_") if "/" in pair else pair[:3] + "_" + pair[3:]
        gran = _TF_MAP.get(timeframe, timeframe)
        resp = await retry_async(
            lambda: client.get(
                f"/v3/instruments/{instrument}/candles",
                params={"granularity": gran, "count": count, "price": "M"},
            ),
            attempts=3,
        )
        resp.raise_for_status()
        raw_candles = resp.json().get("candles", [])
        return [
            normalize_candle(
                {
                    "time": c["time"],
                    "open": c["mid"]["o"],
                    "high": c["mid"]["h"],
                    "low": c["mid"]["l"],
                    "close": c["mid"]["c"],
                    "volume": c.get("volume", 0),
                },
                pair,
                timeframe,
            )
            for c in raw_candles
            if c.get("complete", True)
        ]

    async def get_open_positions(self) -> list[Position]:
        client = self._client_or_raise()
        resp = await retry_async(
            lambda: client.get(f"/v3/accounts/{self._account_id}/openTrades"), attempts=3
        )
        resp.raise_for_status()
        positions: list[Position] = []
        from datetime import datetime, timezone

        for t in resp.json().get("trades", []):
            direction = TradeDirection.BUY if int(t["currentUnits"]) > 0 else TradeDirection.SELL
            positions.append(
                Position(
                    broker_position_id=t["id"],
                    pair=t["instrument"].replace("_", ""),
                    direction=direction,
                    units=abs(int(t["currentUnits"])),
                    open_price=Decimal(t["price"]),
                    current_price=Decimal(t.get("price", t["price"])),
                    unrealized_pnl=Decimal(t.get("unrealizedPL", "0")),
                    opened_at=datetime.fromisoformat(t["openTime"].replace("Z", "+00:00")),
                )
            )
        return positions

    async def place_order(self, order: TradeOrder) -> TradeResult:
        client = self._client_or_raise()
        signal = order.signal
        instrument = signal.pair[:3] + "_" + signal.pair[3:]
        units = order.units if signal.direction == TradeDirection.BUY else -order.units

        body = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "stopLossOnFill": {"price": str(signal.stop_loss)},
                "takeProfitOnFill": {"price": str(signal.take_profit)},
            }
        }
        resp = await retry_async(
            lambda: client.post(
                f"/v3/accounts/{self._account_id}/orders",
                content=json.dumps(body),
            ),
            attempts=3,
        )
        resp.raise_for_status()
        data = resp.json()
        fill = data.get("orderFillTransaction", {})
        from datetime import datetime, timezone

        return TradeResult(
            order=order,
            broker_order_id=fill.get("orderID", ""),
            status=TradeStatus.OPEN if fill else TradeStatus.PENDING,
            fill_price=Decimal(fill["price"]) if fill.get("price") else None,
            opened_at=datetime.now(timezone.utc),
        )

    async def close_position(self, position_id: str) -> TradeResult:
        client = self._client_or_raise()
        resp = await retry_async(
            lambda: client.put(
                f"/v3/accounts/{self._account_id}/trades/{position_id}/close"
            ),
            attempts=3,
        )
        resp.raise_for_status()
        data = resp.json().get("orderFillTransaction", {})
        from datetime import datetime, timezone
        from uuid import uuid4

        from openforexai.models.trade import TradeDirection, TradeSignal

        dummy_signal = TradeSignal(
            pair="",
            direction=TradeDirection.BUY,
            entry_price=Decimal("0"),
            stop_loss=Decimal("0"),
            take_profit=Decimal("0"),
            confidence=0.0,
            reasoning="close",
            generated_at=datetime.now(timezone.utc),
            agent_id="supervisor",
        )
        dummy_order = TradeOrder(
            signal=dummy_signal, units=0, risk_pct=0.0, approved_by="supervisor"
        )
        return TradeResult(
            order=dummy_order,
            broker_order_id=position_id,
            status=TradeStatus.CLOSED,
            fill_price=Decimal(data["price"]) if data.get("price") else None,
            pnl=Decimal(data.get("pl", "0")),
            closed_at=datetime.now(timezone.utc),
        )

    async def stream_ticks(self, pairs: list[str]) -> AsyncIterator[Tick]:
        instruments = ",".join(p[:3] + "_" + p[3:] for p in pairs)
        stream_client = httpx.AsyncClient(
            base_url=self._stream_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=None,
        )
        from datetime import datetime, timezone

        try:
            async with stream_client.stream(
                "GET",
                f"/v3/accounts/{self._account_id}/pricing/stream",
                params={"instruments": instruments},
            ) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") != "PRICE":
                        continue
                    raw_pair = data["instrument"].replace("_", "")
                    yield Tick(
                        pair=raw_pair,
                        bid=Decimal(data["bids"][0]["price"]),
                        ask=Decimal(data["asks"][0]["price"]),
                        timestamp=datetime.now(timezone.utc),
                    )
        finally:
            await stream_client.aclose()
