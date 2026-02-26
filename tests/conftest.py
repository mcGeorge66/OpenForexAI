from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from openforexai.messaging.bus import EventBus
from openforexai.models.market import Candle, MarketSnapshot, Tick
from openforexai.models.trade import (
    Position,
    TradeDirection,
    TradeOrder,
    TradeResult,
    TradeSignal,
    TradeStatus,
)
from openforexai.ports.broker import AbstractBroker
from openforexai.ports.database import AbstractRepository
from openforexai.ports.llm import AbstractLLMProvider, LLMResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_candle(close: float = 1.1000, timeframe: str = "H1") -> Candle:
    return Candle(
        timestamp=datetime.now(timezone.utc),
        open=Decimal(str(close - 0.001)),
        high=Decimal(str(close + 0.002)),
        low=Decimal(str(close - 0.002)),
        close=Decimal(str(close)),
        volume=1000,
        timeframe=timeframe,
    )


def make_tick(pair: str = "EURUSD", bid: float = 1.1000) -> Tick:
    return Tick(
        pair=pair,
        bid=Decimal(str(bid)),
        ask=Decimal(str(bid + 0.0002)),
        timestamp=datetime.now(timezone.utc),
    )


def make_snapshot(pair: str = "EURUSD") -> MarketSnapshot:
    candles = [make_candle(1.1000 + i * 0.0001) for i in range(50)]
    return MarketSnapshot(
        pair=pair,
        current_tick=make_tick(pair),
        candles_h1=candles,
        candles_h4=candles[:10],
        candles_d1=candles[:5],
        session="london",
        snapshot_time=datetime.now(timezone.utc),
    )


# ── Mock broker ───────────────────────────────────────────────────────────────

class MockBroker(AbstractBroker):
    def __init__(self) -> None:
        self.orders: list[TradeOrder] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def get_account_balance(self) -> float:
        return 10_000.0

    async def get_historical_candles(
        self, pair: str, timeframe: str, count: int
    ) -> list[Candle]:
        return [make_candle(1.1000 + i * 0.0001, timeframe) for i in range(min(count, 50))]

    async def get_open_positions(self) -> list[Position]:
        return []

    async def place_order(self, order: TradeOrder) -> TradeResult:
        self.orders.append(order)
        return TradeResult(
            order=order,
            broker_order_id="MOCK_ORDER_001",
            status=TradeStatus.OPEN,
            fill_price=order.signal.entry_price,
            opened_at=datetime.now(timezone.utc),
        )

    async def close_position(self, position_id: str) -> TradeResult:
        signal = TradeSignal(
            pair="EURUSD",
            direction=TradeDirection.BUY,
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            confidence=0.8,
            reasoning="test",
            generated_at=datetime.now(timezone.utc),
            agent_id="test",
        )
        order = TradeOrder(signal=signal, units=1000, risk_pct=1.0, approved_by="supervisor")
        return TradeResult(
            order=order,
            broker_order_id=position_id,
            status=TradeStatus.CLOSED,
            pnl=Decimal("50"),
            closed_at=datetime.now(timezone.utc),
        )

    async def stream_ticks(self, pairs: list[str]) -> AsyncIterator[Tick]:
        for pair in pairs:
            yield make_tick(pair)


# ── Mock LLM ──────────────────────────────────────────────────────────────────

class MockLLMProvider(AbstractLLMProvider):
    def __init__(self, structured_response: dict | None = None) -> None:
        self._structured = structured_response or {
            "action": "BUY",
            "entry_price": 1.1005,
            "stop_loss": 1.0960,
            "take_profit": 1.1090,
            "confidence": 0.75,
            "reasoning": "Mock signal",
            "needs_deep_analysis": False,
        }

    @property
    def model_id(self) -> str:
        return "mock-model"

    async def complete(self, system_prompt, user_message, temperature=0.1, max_tokens=1024):
        return LLMResponse(
            content="Mock LLM response",
            model="mock-model",
            input_tokens=100,
            output_tokens=50,
            raw={},
        )

    async def complete_structured(self, system_prompt, user_message, response_schema):
        return self._structured


# ── Mock repository ───────────────────────────────────────────────────────────

class MockRepository(AbstractRepository):
    def __init__(self) -> None:
        self.trades: list[TradeResult] = []
        self.decisions = []
        self.patterns = []
        self.prompts = []
        self.backtests = []

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def save_trade(self, trade: TradeResult) -> str:
        self.trades.append(trade)
        return str(trade.id)

    async def get_trades(self, pair=None, limit=500) -> list[TradeResult]:
        if pair:
            return [t for t in self.trades if t.order.signal.pair == pair][-limit:]
        return self.trades[-limit:]

    async def save_agent_decision(self, decision) -> str:
        self.decisions.append(decision)
        return str(decision.id)

    async def save_pattern(self, pattern) -> str:
        self.patterns.append(pattern)
        return str(pattern.id)

    async def get_patterns(self, pair=None, limit=100):
        if pair:
            return [p for p in self.patterns if p.pair == pair][-limit:]
        return self.patterns[-limit:]

    async def save_prompt_candidate(self, candidate) -> str:
        self.prompts.append(candidate)
        return str(candidate.id)

    async def get_best_prompt(self, pair):
        active = [p for p in self.prompts if p.pair == pair and p.is_active]
        return active[-1] if active else None

    async def get_prompt_candidates(self, pair):
        return [p for p in self.prompts if p.pair == pair]

    async def save_backtest_result(self, result) -> str:
        self.backtests.append(result)
        return str(result.id)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_broker():
    return MockBroker()


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def mock_repository():
    return MockRepository()


@pytest.fixture
def event_bus():
    return EventBus()
