from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from openforexai.models.trade import OrderBookEntry, OrderStatus, OrderType, Position, TradeDirection
from openforexai.tools.base import ToolContext
from openforexai.tools.trading.place_order import PlaceOrderTool


async def test_place_order_creates_pending_order_book_entry(mock_broker, mock_repository) -> None:
    tool = PlaceOrderTool()
    context = ToolContext(
        agent_id="TEST1-EURUSD-BA-TRADE",
        broker_name=mock_broker.short_name,
        pair="EURUSD",
        broker=mock_broker,
        repository=mock_repository,
    )

    result = await tool.execute(
        {
            "direction": "buy",
            "order_type": "MARKET",
            "units": 1000,
            "entry_price": 1.1000,
            "stop_loss": 1.0950,
            "take_profit": 1.1100,
            "reasoning": "test order",
            "confidence": 0.8,
        },
        context,
    )

    assert result["success"] is True
    assert len(mock_repository.order_book_entries) == 1
    entry = mock_repository.order_book_entries[0]
    assert entry.status == OrderStatus.PENDING
    assert entry.sync_confirmed is False
    assert entry.sync_key
    assert mock_broker.orders[0].sync_key == entry.sync_key


async def test_trigger_sync_matches_existing_entry_by_sync_key(
    mock_broker,
    mock_repository,
    event_bus,
) -> None:
    pending = OrderBookEntry(
        broker_name=mock_broker.short_name,
        broker_order_id=None,
        sync_key="SYNC1234",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        status=OrderStatus.PENDING,
        agent_id="TEST1-EURUSD-BA-TRADE",
        entry_reasoning="pending",
        signal_confidence=0.8,
        market_context_snapshot={},
        requested_at=datetime.now(UTC),
    )
    await mock_repository.save_order_book_entry(pending)
    mock_broker._positions = [
        Position(
            broker_position_id="BRK-1",
            broker_name=mock_broker.short_name,
            pair="EURUSD",
            direction=TradeDirection.BUY,
            units=1000,
            open_price=Decimal("1.1010"),
            current_price=Decimal("1.1010"),
            stop_loss=Decimal("1.0950"),
            take_profit=Decimal("1.1100"),
            unrealized_pnl=Decimal("0"),
            opened_at=datetime.now(UTC),
            sync_key="SYNC1234",
        )
    ]

    found = await mock_broker.trigger_sync("EURUSD", mock_repository, event_bus)

    assert found == []
    assert len(mock_repository.order_book_entries) == 1
    entry = mock_repository.order_book_entries[0]
    assert entry.broker_order_id == "BRK-1"
    assert entry.status == OrderStatus.OPEN
    assert entry.sync_confirmed is True


async def test_trigger_sync_imports_unmatched_broker_position(
    mock_broker,
    mock_repository,
    event_bus,
) -> None:
    mock_broker._positions = [
        Position(
            broker_position_id="BRK-2",
            broker_name=mock_broker.short_name,
            pair="EURUSD",
            direction=TradeDirection.SELL,
            units=2000,
            open_price=Decimal("1.1020"),
            current_price=Decimal("1.1015"),
            stop_loss=None,
            take_profit=None,
            unrealized_pnl=Decimal("5"),
            opened_at=datetime.now(UTC),
            sync_key="SYNC9999",
        )
    ]

    await mock_broker.trigger_sync("EURUSD", mock_repository, event_bus)

    assert len(mock_repository.order_book_entries) == 1
    entry = mock_repository.order_book_entries[0]
    assert entry.broker_order_id == "BRK-2"
    assert entry.sync_key == "SYNC9999"
    assert entry.status == OrderStatus.OPEN
    assert entry.sync_confirmed is True
