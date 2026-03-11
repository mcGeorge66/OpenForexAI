from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from openforexai.messaging.bus import EventBus
from openforexai.models.account import AccountStatus
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
from openforexai.ports.llm import (
    AbstractLLMProvider,
    LLMResponse,
    LLMResponseWithTools,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

MOCK_BROKER_NAME = "MOCKB"


def make_candle(close: float = 1.1000, timeframe: str = "H1") -> Candle:
    return Candle(
        timestamp=datetime.now(UTC),
        open=Decimal(str(close - 0.001)),
        high=Decimal(str(close + 0.002)),
        low=Decimal(str(close - 0.002)),
        close=Decimal(str(close)),
        tick_volume=1000,
        spread=Decimal("0.0002"),
        timeframe=timeframe,
    )


def make_tick(pair: str = "EURUSD", bid: float = 1.1000) -> Tick:
    return Tick(
        pair=pair,
        bid=Decimal(str(bid)),
        ask=Decimal(str(bid + 0.0002)),
        timestamp=datetime.now(UTC),
    )


def make_snapshot(pair: str = "EURUSD", broker_name: str = MOCK_BROKER_NAME) -> MarketSnapshot:
    candles = [make_candle(1.1000 + i * 0.0001, "M5") for i in range(50)]
    return MarketSnapshot(
        pair=pair,
        broker_name=broker_name,
        current_tick=make_tick(pair),
        candles_m5=candles,
        candles_m15=candles[:20],
        candles_m30=candles[:10],
        candles_h1=candles[:10],
        candles_h4=candles[:5],
        candles_d1=candles[:3],
        session="london",
        snapshot_time=datetime.now(UTC),
    )


def make_account_status(broker_name: str = MOCK_BROKER_NAME) -> AccountStatus:
    return AccountStatus(
        broker_name=broker_name,
        balance=Decimal("10000.00"),
        equity=Decimal("10050.00"),
        margin=Decimal("200.00"),
        margin_free=Decimal("9850.00"),
        leverage=50,
        currency="USD",
        trade_allowed=True,
        margin_level=5025.0,
        recorded_at=datetime.now(UTC),
    )


# ── Mock broker ───────────────────────────────────────────────────────────────

class MockBroker(AbstractBroker):
    def __init__(self, broker_name: str = MOCK_BROKER_NAME) -> None:
        self._short_name = broker_name
        self.orders: list[TradeOrder] = []
        self._positions: list[Position] = []

    @property
    def short_name(self) -> str:
        return self._short_name

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def fetch_latest_m5_candle(self, pair: str) -> Candle | None:
        return make_candle(1.1000, "M5")

    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        return [make_candle(1.1000 + i * 0.0001, "M5") for i in range(min(count, 50))]

    async def get_account_status(self) -> AccountStatus:
        return make_account_status(self._short_name)

    async def get_open_positions(self) -> list[Position]:
        return list(self._positions)

    async def place_order(self, order: TradeOrder) -> TradeResult:
        self.orders.append(order)
        return TradeResult(
            order=order,
            broker_order_id="MOCK_ORDER_001",
            status=TradeStatus.OPEN,
            fill_price=order.signal.entry_price,
            opened_at=datetime.now(UTC),
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
            generated_at=datetime.now(UTC),
            agent_id="test",
        )
        order = TradeOrder(signal=signal, units=1000, risk_pct=1.0, approved_by="supervisor")
        return TradeResult(
            order=order,
            broker_order_id=position_id,
            status=TradeStatus.CLOSED,
            pnl=Decimal("50"),
            closed_at=datetime.now(UTC),
        )


# ── Mock LLM ──────────────────────────────────────────────────────────────────

class MockLLMProvider(AbstractLLMProvider):
    """Mock LLM that returns a configurable plain-text response.

    ``complete_with_tools()`` returns a text-only response (no tool calls)
    so the tool-use loop in BaseAgent terminates after the first turn.
    """

    def __init__(
        self,
        response_text: str = "Mock LLM decision — HOLD",
        structured_response: dict[str, Any] | None = None,
    ) -> None:
        self._response_text = response_text
        self._structured = structured_response or {}

    @property
    def model_id(self) -> str:
        return "mock-model"

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        return LLMResponse(
            content=self._response_text,
            model="mock-model",
            input_tokens=100,
            output_tokens=50,
            raw={},
        )

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type,
    ) -> dict[str, Any]:
        return self._structured

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponseWithTools:
        return LLMResponseWithTools(
            content=self._response_text,
            tool_calls=[],
            stop_reason="end_turn",
            model="mock-model",
            input_tokens=100,
            output_tokens=50,
        )


# ── Mock repository ───────────────────────────────────────────────────────────

class MockRepository(AbstractRepository):
    def __init__(self) -> None:
        self.trades: list[TradeResult] = []
        self.decisions: list = []
        self.patterns: list = []
        self.prompts: list = []
        self.backtests: list = []
        self.account_statuses: list[AccountStatus] = []
        self.candles: dict[tuple, list[Candle]] = {}
        self.order_book_entries: list = []

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    # ── Candles ──────────────────────────────────────────────────────────────

    async def save_candle(self, broker_name: str, pair: str, candle: Candle) -> None:
        key = (broker_name, pair, candle.timeframe)
        self.candles.setdefault(key, []).append(candle)

    async def save_candles_bulk(
        self, broker_name: str, pair: str, candles: list[Candle]
    ) -> None:
        for c in candles:
            await self.save_candle(broker_name, pair, c)

    async def get_candles(
        self, broker_name: str, pair: str, timeframe: str, limit: int = 500
    ) -> list[Candle]:
        key = (broker_name, pair, timeframe)
        return list(self.candles.get(key, []))[-limit:]

    async def get_candle_count(self, broker_name: str, pair: str, timeframe: str) -> int:
        key = (broker_name, pair, timeframe)
        return len(self.candles.get(key, []))

    # ── Account status ────────────────────────────────────────────────────────

    async def save_account_status(self, status: AccountStatus) -> None:
        self.account_statuses.append(status)

    async def get_latest_account_status(self, broker_name: str) -> AccountStatus | None:
        matching = [s for s in self.account_statuses if s.broker_name == broker_name]
        return matching[-1] if matching else None

    # ── Order book ────────────────────────────────────────────────────────────

    async def save_order_book_entry(self, entry) -> str:
        self.order_book_entries.append(entry)
        return str(entry.id)

    async def update_order_book_entry(self, entry_id: str, updates: dict) -> None:
        for entry in self.order_book_entries:
            if str(entry.id) == entry_id:
                for k, v in updates.items():
                    setattr(entry, k, v)
                break

    async def get_order_book_entry(self, entry_id: str):
        for entry in self.order_book_entries:
            if str(entry.id) == entry_id:
                return entry
        return None

    async def get_open_order_book_entries(self, broker_name: str) -> list:
        return [e for e in self.order_book_entries if e.broker_name == broker_name]

    async def get_order_book_entries(
        self, broker_name: str, pair: str | None = None, limit: int = 200
    ) -> list:
        entries = [e for e in self.order_book_entries if e.broker_name == broker_name]
        if pair:
            entries = [e for e in entries if e.pair == pair]
        return entries[-limit:]

    # ── Trades ────────────────────────────────────────────────────────────────

    async def save_trade(self, trade: TradeResult) -> str:
        self.trades.append(trade)
        return str(trade.id)

    async def get_trades(self, pair: str | None = None, limit: int = 500) -> list[TradeResult]:
        if pair:
            return [t for t in self.trades if t.order.signal.pair == pair][-limit:]
        return self.trades[-limit:]

    # ── Agent decisions ───────────────────────────────────────────────────────

    async def save_agent_decision(self, decision) -> str:
        self.decisions.append(decision)
        return str(decision.id)

    # ── Optimization ─────────────────────────────────────────────────────────

    async def save_pattern(self, pattern) -> str:
        self.patterns.append(pattern)
        return str(pattern.id)

    async def get_patterns(self, pair: str | None = None, limit: int = 100) -> list:
        if pair:
            return [p for p in self.patterns if p.pair == pair][-limit:]
        return self.patterns[-limit:]

    async def save_prompt_candidate(self, candidate) -> str:
        self.prompts.append(candidate)
        return str(candidate.id)

    async def get_best_prompt(self, pair: str):
        active = [p for p in self.prompts if p.pair == pair and p.is_active]
        return active[-1] if active else None

    async def get_prompt_candidates(self, pair: str) -> list:
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
