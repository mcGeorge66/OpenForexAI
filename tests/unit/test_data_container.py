from __future__ import annotations

import pytest

from openforexai.messaging.bus import EventBus
from tests.conftest import MOCK_BROKER_NAME, MockBroker, MockRepository


def _make_container(pairs: list[str] | None = None):
    from openforexai.data.container import DataContainer

    pairs = pairs or ["EURUSD"]
    broker = MockBroker()
    repo = MockRepository()
    bus = EventBus()

    container = DataContainer(store=repo, event_bus=bus)
    container.register_broker(broker, pairs)
    return container, broker


@pytest.mark.asyncio
async def test_initialize_loads_candles():
    container, _ = _make_container()
    await container.initialize()
    candles = await container.get_candles(MOCK_BROKER_NAME, "EURUSD", "H1")
    assert len(candles) > 0


@pytest.mark.asyncio
async def test_get_snapshot_returns_snapshot():
    container, _ = _make_container()
    await container.initialize()
    snapshot = await container.get_snapshot(MOCK_BROKER_NAME, "EURUSD")
    assert snapshot.pair == "EURUSD"
    assert snapshot.candles_h1


@pytest.mark.asyncio
async def test_unknown_pair_is_initialized_on_demand():
    container, _ = _make_container()
    await container.initialize()
    with pytest.raises(ValueError, match="GBPUSD"):
        await container.get_snapshot(MOCK_BROKER_NAME, "GBPUSD")

