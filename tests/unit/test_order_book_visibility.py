from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from openforexai.models.trade import (
    CloseReason,
    OrderBookEntry,
    OrderStatus,
    OrderType,
    Position,
    TradeDirection,
)
from openforexai.tools.base import ToolContext
from openforexai.tools.orderbook.get_order_book import GetOrderBookTool
from openforexai.tools.trading.auto_place_order import AutoPlaceOrderTool
from openforexai.tools.trading.close_position import ClosePositionTool
from openforexai.tools.trading.modify_order import ModifyOrderTool


def _entry(status: OrderStatus, broker_order_id: str) -> OrderBookEntry:
    now = datetime.now(UTC)
    return OrderBookEntry(
        broker_name="MOCKB",
        broker_order_id=broker_order_id,
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        fill_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        status=status,
        agent_id="TEST",
        entry_reasoning="test",
        signal_confidence=0.6,
        market_context_snapshot={"source": "test"},
        requested_at=now,
        opened_at=now if status != OrderStatus.REJECTED else None,
        sync_confirmed=status != OrderStatus.REJECTED,
    )


async def test_get_order_book_can_filter_closed_and_rejected(mock_repository) -> None:
    await mock_repository.save_order_book_entry(_entry(OrderStatus.OPEN, "101"))
    await mock_repository.save_order_book_entry(_entry(OrderStatus.CLOSED, "102"))
    await mock_repository.save_order_book_entry(_entry(OrderStatus.REJECTED, "103"))

    tool = GetOrderBookTool()
    context = ToolContext(agent_id="TEST", broker_name="MOCKB", repository=mock_repository)

    closed = await tool.execute({"status_filter": "closed"}, context)
    rejected = await tool.execute({"status_filter": "rejected"}, context)

    assert len(closed) == 1
    assert closed[0]["broker_order_id"] == "102"
    assert closed[0]["status"] == "CLOSED"
    assert len(rejected) == 1
    assert rejected[0]["broker_order_id"] == "103"
    assert rejected[0]["status"] == "REJECTED"


async def test_close_position_updates_order_book_with_close_data(
    mock_broker,
    mock_repository,
) -> None:
    now = datetime.now(UTC)
    entry = OrderBookEntry(
        broker_name="MOCKB",
        broker_order_id="POS123",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        fill_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        status=OrderStatus.OPEN,
        agent_id="TEST",
        entry_reasoning="test",
        signal_confidence=0.6,
        market_context_snapshot={"source": "test"},
        requested_at=now,
        opened_at=now,
        sync_confirmed=True,
    )
    await mock_repository.save_order_book_entry(entry)

    tool = ClosePositionTool()
    context = ToolContext(
        agent_id="TEST",
        broker_name="MOCKB",
        broker=mock_broker,
        repository=mock_repository,
    )

    result = await tool.execute({"position_id": "POS123", "reasoning": "manual exit"}, context)
    updated = await mock_repository.get_order_book_entry(str(entry.id))

    assert result["success"] is True
    assert result["order_book_entry_id"] == str(entry.id)
    assert updated is not None
    assert updated.status == OrderStatus.CLOSED
    assert updated.close_reason == CloseReason.AGENT_CLOSED
    assert updated.close_reasoning == "manual exit"
    assert updated.pnl_account_currency == Decimal("50")


async def test_modify_order_updates_order_book_limits(mock_broker, mock_repository) -> None:
    now = datetime.now(UTC)
    entry = OrderBookEntry(
        broker_name="MOCKB",
        broker_order_id="POS124",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        fill_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        status=OrderStatus.OPEN,
        agent_id="TEST",
        entry_reasoning="test",
        signal_confidence=0.6,
        market_context_snapshot={"source": "test"},
        requested_at=now,
        opened_at=now,
        sync_confirmed=True,
    )
    await mock_repository.save_order_book_entry(entry)

    tool = ModifyOrderTool()
    context = ToolContext(
        agent_id="TEST",
        broker_name="MOCKB",
        broker=mock_broker,
        repository=mock_repository,
    )

    result = await tool.execute(
        {"position_id": "POS124", "stop_loss": 1.0975, "take_profit": 1.1150},
        context,
    )
    updated = await mock_repository.get_order_book_entry(str(entry.id))

    assert result["success"] is True
    assert result["order_book_entry_id"] == str(entry.id)
    assert updated is not None
    assert updated.stop_loss == Decimal("1.0975")
    assert updated.take_profit == Decimal("1.1150")


async def test_close_position_partial_updates_remaining_units(
    mock_broker,
    mock_repository,
) -> None:
    now = datetime.now(UTC)
    entry = OrderBookEntry(
        broker_name="MOCKB",
        broker_order_id="POS125",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        fill_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        status=OrderStatus.OPEN,
        agent_id="TEST",
        entry_reasoning="test",
        signal_confidence=0.6,
        market_context_snapshot={"source": "test"},
        requested_at=now,
        opened_at=now,
        sync_confirmed=True,
    )
    await mock_repository.save_order_book_entry(entry)

    tool = ClosePositionTool()
    context = ToolContext(
        agent_id="TEST",
        broker_name="MOCKB",
        broker=mock_broker,
        repository=mock_repository,
    )

    result = await tool.execute({"position_id": "POS125", "units": 400}, context)
    updated = await mock_repository.get_order_book_entry(str(entry.id))

    assert result["success"] is True
    assert result["status"] == "OPEN"
    assert result["closed_units"] == 400
    assert result["remaining_units"] == 600
    assert updated is not None
    assert updated.status == OrderStatus.OPEN
    assert updated.units == 600


async def test_auto_place_order_uses_defaults_and_risk_sizing(
    mock_broker,
    mock_repository,
) -> None:
    tool = AutoPlaceOrderTool()
    context = ToolContext(
        agent_id="TEST",
        broker_name="MOCKB",
        pair="EURUSD",
        broker=mock_broker,
        repository=mock_repository,
    )

    result = await tool.execute(
        {
            "direction": "buy",
        },
        context,
    )

    assert result["success"] is True
    assert len(mock_repository.order_book_entries) == 1
    entry = mock_repository.order_book_entries[0]
    assert entry.order_type == OrderType.MARKET
    assert entry.units > 0
    assert entry.stop_loss is not None
    assert entry.take_profit is not None


async def test_close_position_zero_closes_all_matching_positions(
    mock_broker,
    mock_repository,
) -> None:
    now = datetime.now(UTC)
    first = OrderBookEntry(
        broker_name="MOCKB",
        broker_order_id="POS201",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        fill_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        status=OrderStatus.OPEN,
        agent_id="TEST",
        entry_reasoning="test",
        signal_confidence=0.6,
        market_context_snapshot={"source": "test"},
        requested_at=now,
        opened_at=now,
        sync_confirmed=True,
    )
    second = first.model_copy(update={"broker_order_id": "POS202"})
    await mock_repository.save_order_book_entry(first)
    await mock_repository.save_order_book_entry(second)
    mock_broker._positions = [
        Position(
            broker_position_id="POS201",
            broker_name="MOCKB",
            pair="EURUSD",
            direction=TradeDirection.BUY,
            units=1000,
            open_price=Decimal("1.1000"),
            current_price=Decimal("1.1010"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            unrealized_pnl=Decimal("10"),
            opened_at=now,
            sync_key=None,
        ),
        Position(
            broker_position_id="POS202",
            broker_name="MOCKB",
            pair="EURUSD",
            direction=TradeDirection.BUY,
            units=1000,
            open_price=Decimal("1.1000"),
            current_price=Decimal("1.1010"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            unrealized_pnl=Decimal("10"),
            opened_at=now,
            sync_key=None,
        ),
    ]

    tool = ClosePositionTool()
    context = ToolContext(
        agent_id="TEST",
        broker_name="MOCKB",
        pair="EURUSD",
        broker=mock_broker,
        repository=mock_repository,
    )

    result = await tool.execute({"position_id": "0", "reasoning": "panic exit"}, context)

    assert result["success"] is True
    assert result["closed_count"] == 2
