from __future__ import annotations

import pytest

from tests.conftest import MockBroker, MockRepository


@pytest.mark.asyncio
async def test_initialize_loads_candles():
    from openforexai.data.container import DataContainer

    broker = MockBroker()
    repository = MockRepository()
    container = DataContainer(
        broker=broker,
        repository=repository,
        pairs=["EURUSD"],
        rolling_weeks=1,
        timeframes=["H1"],
    )
    await container.initialize()
    candles = container.get_candles("EURUSD", "H1")
    assert len(candles) > 0


@pytest.mark.asyncio
async def test_get_snapshot_returns_snapshot():
    from openforexai.data.container import DataContainer

    broker = MockBroker()
    repository = MockRepository()
    container = DataContainer(
        broker=broker,
        repository=repository,
        pairs=["EURUSD"],
        rolling_weeks=1,
        timeframes=["H1", "H4", "D1"],
    )
    await container.initialize()
    snapshot = await container.get_snapshot("EURUSD")
    assert snapshot.pair == "EURUSD"
    assert snapshot.candles_h1


@pytest.mark.asyncio
async def test_unknown_pair_raises():
    from openforexai.data.container import DataContainer

    broker = MockBroker()
    repository = MockRepository()
    container = DataContainer(
        broker=broker,
        repository=repository,
        pairs=["EURUSD"],
        rolling_weeks=1,
    )
    await container.initialize()
    with pytest.raises(ValueError, match="GBPUSD"):
        await container.get_snapshot("GBPUSD")
