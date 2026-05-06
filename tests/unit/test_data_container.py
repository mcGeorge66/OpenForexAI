from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from openforexai.messaging.bus import EventBus
from openforexai.models.market import Candle
from openforexai.models.monitoring import MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus
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
    snapshot = await container.get_snapshot(MOCK_BROKER_NAME, "GBPUSD")
    assert snapshot.pair == "GBPUSD"
    assert snapshot.candles_h1


def _make_m5_series(start: datetime, count: int, base_close: Decimal) -> list[Candle]:
    candles: list[Candle] = []
    for idx in range(count):
        close = base_close + (Decimal("0.0001") * idx)
        candles.append(Candle(
            timestamp=start + timedelta(minutes=5 * idx),
            open=close - Decimal("0.0002"),
            high=close + Decimal("0.0003"),
            low=close - Decimal("0.0003"),
            close=close,
            tick_volume=1000 + idx,
            spread=Decimal("0.0001"),
            timeframe="M5",
        ))
    return candles


class FreshReadBroker(MockBroker):
    def __init__(self, fresh_candles: list[Candle]) -> None:
        super().__init__()
        self.fresh_candles = fresh_candles
        self.requested_counts: list[int] = []

    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        self.requested_counts.append(count)
        return self.fresh_candles[-count:]


class NewestFirstMockRepository(MockRepository):
    async def get_candles(
        self, broker_name: str, pair: str, timeframe: str, limit: int = 500
    ) -> list[Candle]:
        key = (broker_name, pair, timeframe)
        return list(reversed(self.candles.get(key, [])))[0:limit]


class UpsertingMockRepository(MockRepository):
    async def save_candle(self, broker_name: str, pair: str, candle: Candle) -> None:
        key = (broker_name, pair, candle.timeframe)
        series = self.candles.setdefault(key, [])
        for idx, existing in enumerate(series):
            if existing.timestamp == candle.timestamp:
                series[idx] = candle
                return
        series.append(candle)


@pytest.mark.asyncio
async def test_get_candles_refreshes_stale_but_contiguous_m5_data():
    from openforexai.data.container import DataContainer

    repo = NewestFirstMockRepository()
    bus = EventBus()

    latest_completed = DataContainer._latest_completed_m5_open()
    stale_start = latest_completed - timedelta(days=30, minutes=5 * 19)
    fresh_start = latest_completed - timedelta(minutes=5 * 19)

    stale_candles = _make_m5_series(stale_start, 20, Decimal("1.0500"))
    fresh_candles = _make_m5_series(fresh_start, 20, Decimal("1.1500"))

    await repo.save_candles_bulk(MOCK_BROKER_NAME, "EURUSD", stale_candles)

    broker = FreshReadBroker(fresh_candles)
    container = DataContainer(store=repo, event_bus=bus)
    container.register_broker(broker, ["EURUSD"])

    candles = await container.get_candles(MOCK_BROKER_NAME, "EURUSD", "M5", limit=20)

    assert broker.requested_counts
    assert len(candles) == 20
    assert candles[-1].timestamp == fresh_candles[-1].timestamp
    assert candles[-1].close == fresh_candles[-1].close


@pytest.mark.asyncio
async def test_get_candles_emits_visible_monitoring_events_for_read_refresh():
    from openforexai.data.container import DataContainer

    repo = NewestFirstMockRepository()
    bus = EventBus()
    monitoring = MonitoringBus(detail_level="INFO")

    latest_completed = DataContainer._latest_completed_m5_open()
    stale_start = latest_completed - timedelta(days=30, minutes=5 * 19)
    fresh_start = latest_completed - timedelta(minutes=5 * 19)

    await repo.save_candles_bulk(
        MOCK_BROKER_NAME,
        "EURUSD",
        _make_m5_series(stale_start, 20, Decimal("1.0500")),
    )

    broker = FreshReadBroker(_make_m5_series(fresh_start, 20, Decimal("1.1500")))
    container = DataContainer(store=repo, event_bus=bus, monitoring_bus=monitoring)
    container.register_broker(broker, ["EURUSD"])

    await container.get_candles(MOCK_BROKER_NAME, "EURUSD", "M5", limit=20)

    events = monitoring.recent_events(limit=20)
    event_types = [event.event_type for event in events]
    assert MonitoringEventType.CANDLE_REPAIR_STARTED in event_types
    assert MonitoringEventType.CANDLE_REPAIR_COMPLETED in event_types


@pytest.mark.asyncio
async def test_m5_update_upserts_same_timestamp_for_building_candle():
    from openforexai.data.container import DataContainer
    from openforexai.models.messaging import AgentMessage, EventType

    repo = UpsertingMockRepository()
    bus = EventBus()
    container = DataContainer(store=repo, event_bus=bus)
    container.register_broker(MockBroker(), ["EURUSD"])

    first = _make_m5_series(datetime(2026, 5, 6, 6, 30, tzinfo=UTC), 1, Decimal("1.1000"))[0]
    second = first.model_copy(update={"close": Decimal("1.1015"), "high": Decimal("1.1015")})

    await container._on_m5_candle(AgentMessage(
        event_type=EventType.M5_CANDLE_UPDATE,
        source_agent_id="TEST1-EURUSD-AD-ADPT",
        payload={
            "broker_name": MOCK_BROKER_NAME,
            "pair": "EURUSD",
            "candle": first.model_dump(mode="json"),
        },
    ))
    await container._on_m5_candle(AgentMessage(
        event_type=EventType.M5_CANDLE_UPDATE,
        source_agent_id="TEST1-EURUSD-AD-ADPT",
        payload={
            "broker_name": MOCK_BROKER_NAME,
            "pair": "EURUSD",
            "candle": second.model_dump(mode="json"),
        },
    ))

    candles = await repo.get_candles(MOCK_BROKER_NAME, "EURUSD", "M5")
    assert len(candles) == 1
    assert candles[0].close == Decimal("1.1015")

