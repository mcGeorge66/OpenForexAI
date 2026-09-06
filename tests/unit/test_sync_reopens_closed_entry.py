from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from openforexai.adapters.brokers.base import BrokerBase
from openforexai.messaging.bus import EventBus
from openforexai.models.trade import (
    OrderBookEntry,
    OrderStatus,
    OrderType,
    Position,
    TradeDirection,
)
from openforexai.repository_service import RepositoryService
from tests.conftest import MockRepository


class _TestBroker(BrokerBase):
    """Minimal BrokerBase subclass — MockBroker in conftest.py only implements
    the pure AbstractBroker data port, not BrokerBase's sync-loop orchestration
    (_sync_pair/trigger_sync live on BrokerBase), so a local double is needed
    here instead."""

    def __init__(self, broker_name: str) -> None:
        super().__init__(monitoring_bus=None)
        self._short_name = broker_name
        self._positions: list[Position] = []

    @property
    def short_name(self) -> str:
        return self._short_name

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def fetch_latest_m5_candle(self, pair: str):
        return None

    async def get_historical_m5_candles(self, pair: str, count: int):
        return []

    async def get_account_status(self):
        raise NotImplementedError

    async def place_order(self, order):
        raise NotImplementedError

    async def modify_position(self, position_id: str, stop_loss=None, take_profit=None):
        raise NotImplementedError

    async def close_position(self, position_id: str, units: int | None = None):
        raise NotImplementedError

    async def get_open_positions(self) -> list[Position]:
        return list(self._positions)


def _make_closed_entry(**overrides) -> OrderBookEntry:
    defaults = dict(
        broker_name="OXS_T",
        broker_order_id="99001",
        sync_key="SYNCKEY99001",
        pair="EURUSD",
        direction=TradeDirection.SELL,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1613"),
        fill_price=Decimal("1.1613"),
        stop_loss=Decimal("1.1620"),
        take_profit=Decimal("1.1600"),
        status=OrderStatus.CLOSED,
        agent_id="OXS_T-ALL___-BA-ANLYS",
        entry_reasoning="test",
        signal_confidence=0.7,
        market_context_snapshot={},
        requested_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
        close_reason="SYNC_DETECTED",
        pnl_account_currency=Decimal("-5"),
    )
    defaults.update(overrides)
    return OrderBookEntry(**defaults)


async def _run_sync_scenario(broker_position: Position, closed_entry: OrderBookEntry):
    """Wires a real EventBus + RepositoryService(MockRepository) and runs one
    _sync_pair pass for a broker position that matches a local entry which is
    NOT currently OPEN — the scenario this fix targets: an earlier sync pass
    wrongly closed a still-live position, and the broker now reports it open
    again. Returns the repository's order_book_entries list after the sync."""
    bus = EventBus()
    repo = MockRepository()
    repo.order_book_entries.append(closed_entry)
    service = RepositoryService(repo, bus, monitoring_bus=None)
    # publish() only enqueues onto bus._inbound — actual routing/delivery (including
    # resolving _repo_request's pending response futures) happens in the dispatch
    # loop, which must be running as its own task, exactly like in the real system.
    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())
    service_task = asyncio.create_task(service.run())
    try:
        broker = _TestBroker("OXS_T")
        broker._positions = [broker_position]
        await broker.trigger_sync("EURUSD", bus)
        return repo.order_book_entries
    finally:
        bus.stop()
        for task in (service_task, dispatch_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@pytest.mark.asyncio
async def test_reopens_the_same_entry_instead_of_importing_a_duplicate() -> None:
    closed_entry = _make_closed_entry()
    broker_position = Position(
        broker_position_id="99001",
        broker_name="OXS_T",
        pair="EURUSD",
        direction=TradeDirection.SELL,
        units=1000,
        open_price=Decimal("1.1613"),
        current_price=Decimal("1.1605"),
        stop_loss=Decimal("1.1620"),
        take_profit=Decimal("1.1600"),
        unrealized_pnl=Decimal("8"),
        opened_at=datetime.now(UTC),
        sync_key="SYNCKEY99001",
    )

    entries = await _run_sync_scenario(broker_position, closed_entry)

    assert len(entries) == 1, "must re-sync the existing row, never add a second one"
    entry = entries[0]
    assert str(entry.id) == str(closed_entry.id)
    assert entry.status == OrderStatus.OPEN
    assert entry.closed_at is None
    assert entry.close_reason is None
    assert entry.pnl_account_currency is None


@pytest.mark.asyncio
async def test_matches_by_sync_key_when_broker_order_id_absent_locally() -> None:
    """Same scenario, but the local entry never got a broker_order_id persisted
    (e.g. it closed before that field was confirmed) — sync_key alone must still
    find it."""
    closed_entry = _make_closed_entry(broker_order_id=None)
    broker_position = Position(
        broker_position_id="99002",
        broker_name="OXS_T",
        pair="EURUSD",
        direction=TradeDirection.SELL,
        units=1000,
        open_price=Decimal("1.1613"),
        current_price=Decimal("1.1605"),
        stop_loss=Decimal("1.1620"),
        take_profit=Decimal("1.1600"),
        unrealized_pnl=Decimal("8"),
        opened_at=datetime.now(UTC),
        sync_key="SYNCKEY99001",
    )

    entries = await _run_sync_scenario(broker_position, closed_entry)

    assert len(entries) == 1
    entry = entries[0]
    assert str(entry.id) == str(closed_entry.id)
    assert entry.status == OrderStatus.OPEN
    assert entry.broker_order_id == "99002"


@pytest.mark.asyncio
async def test_genuinely_new_position_still_gets_imported() -> None:
    """No local entry at all (any status) shares this broker_order_id/sync_key —
    this really is a new, never-seen position, so importing it is correct."""
    broker_position = Position(
        broker_position_id="99003",
        broker_name="OXS_T",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        units=1000,
        open_price=Decimal("1.1700"),
        current_price=Decimal("1.1702"),
        stop_loss=None,
        take_profit=None,
        unrealized_pnl=Decimal("2"),
        opened_at=datetime.now(UTC),
        sync_key="SYNCKEY-NEW",
    )

    bus = EventBus()
    repo = MockRepository()
    service = RepositoryService(repo, bus, monitoring_bus=None)
    dispatch_task = asyncio.create_task(bus.start_dispatch_loop())
    service_task = asyncio.create_task(service.run())
    try:
        broker = _TestBroker("OXS_T")
        broker._positions = [broker_position]
        await broker.trigger_sync("EURUSD", bus)
        entries = repo.order_book_entries
    finally:
        bus.stop()
        for task in (service_task, dispatch_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    assert len(entries) == 1
    assert entries[0].agent_id == "broker_sync"
    assert entries[0].broker_order_id == "99003"
    assert entries[0].status == OrderStatus.OPEN
