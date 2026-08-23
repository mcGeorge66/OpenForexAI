from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from openforexai.models.messaging import AgentMessage, EventType
from openforexai.models.trade import OrderType, TradeDirection
from openforexai.repository_service import REPO_SERVICE_ID, RepositoryService
from tests.conftest import MockRepository


class _FakeBus:
    """Records every published AgentMessage; no routing/delivery semantics needed
    for these tests — RepositoryService._publish_position_closed is tested as a
    unit, not the end-to-end bus delivery to a subscribing agent."""

    def __init__(self) -> None:
        self.published: list[AgentMessage] = []

    def register_member(self, member_id: str, maxsize: int = 0):
        import asyncio
        return asyncio.Queue()

    async def publish(self, message: AgentMessage, *, triggered_by: AgentMessage | None = None) -> None:
        self.published.append(message)


def _make_service():
    repo = MockRepository()
    bus = _FakeBus()
    service = RepositoryService(repo, bus, monitoring_bus=None)
    return service, repo, bus


def _make_entry(**overrides):
    from openforexai.models.trade import OrderBookEntry

    defaults = dict(
        broker_name="mt5_oxs_t",
        pair="EURUSD",
        direction=TradeDirection.BUY,
        order_type=OrderType.MARKET,
        units=1000,
        requested_price=Decimal("1.1000"),
        agent_id="OXS_T-EURUSD-AA-ANLYS",
        entry_reasoning="test",
        signal_confidence=0.8,
        market_context_snapshot={},
        requested_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    entry = OrderBookEntry(**defaults)
    return entry


def _request_msg(operation: str, args: dict) -> AgentMessage:
    return AgentMessage(
        event_type=EventType.REPO_REQUEST,
        source_agent_id="TEST-CALLER",
        payload={"operation": operation, "args": args},
    )


@pytest.mark.asyncio
async def test_closing_an_order_publishes_position_closed():
    service, repo, bus = _make_service()
    entry = _make_entry()
    repo.order_book_entries.append(entry)

    msg = _request_msg("update_order_book_entry", {
        "entry_id": str(entry.id),
        "updates": {"status": "CLOSED", "close_price": "1.1050"},
    })
    await service._handle(msg)

    closed_events = [m for m in bus.published if m.event_type == EventType.POSITION_CLOSED]
    assert len(closed_events) == 1
    published = closed_events[0]
    assert published.source_agent_id == REPO_SERVICE_ID
    assert published.target_agent_id is None  # broadcast, not directed at the caller
    assert published.payload["id"] == str(entry.id)
    assert published.payload["pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_non_close_update_does_not_publish_position_closed():
    service, repo, bus = _make_service()
    entry = _make_entry()
    repo.order_book_entries.append(entry)

    msg = _request_msg("update_order_book_entry", {
        "entry_id": str(entry.id),
        "updates": {"broker_order_id": "12345"},
    })
    await service._handle(msg)

    assert not any(m.event_type == EventType.POSITION_CLOSED for m in bus.published)


@pytest.mark.asyncio
async def test_other_operations_never_publish_position_closed():
    service, repo, bus = _make_service()
    entry = _make_entry()
    repo.order_book_entries.append(entry)

    msg = _request_msg("get_order_book_entry", {"entry_id": str(entry.id)})
    await service._handle(msg)

    assert not any(m.event_type == EventType.POSITION_CLOSED for m in bus.published)


@pytest.mark.asyncio
async def test_close_of_unknown_entry_does_not_crash_or_publish():
    service, repo, bus = _make_service()

    msg = _request_msg("update_order_book_entry", {
        "entry_id": str(uuid4()),
        "updates": {"status": "CLOSED"},
    })
    await service._handle(msg)  # update_order_book_entry on MockRepository is a no-op if not found

    assert not any(m.event_type == EventType.POSITION_CLOSED for m in bus.published)
    # And the REPO_RESPONSE still went out with no error, exactly as before this feature.
    responses = [m for m in bus.published if m.event_type == EventType.REPO_RESPONSE]
    assert len(responses) == 1
    assert responses[0].payload["error"] is None
