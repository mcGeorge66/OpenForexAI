from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from openforexai.adapters.brokers.base import BrokerBase
from openforexai.messaging.bus import EventBus
from openforexai.models.account import AccountStatus
from openforexai.models.market import Candle
from openforexai.models.messaging import EventType
from openforexai.models.trade import Position, TradeOrder, TradeResult


def _make_m5_candle(ts: datetime, close: str) -> Candle:
    return Candle(
        timestamp=ts,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        tick_volume=100,
        spread=Decimal("0.0001"),
        timeframe="M5",
    )


class TriggerPublishingBroker(BrokerBase):
    def __init__(self, responses: list[list[Candle]]) -> None:
        super().__init__()
        self._responses = responses
        self._fetch_calls = 0

    @property
    def short_name(self) -> str:
        return "TEST1"

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def fetch_latest_m5_candle(self, pair: str) -> Candle | None:
        return None

    async def get_historical_m5_candles(self, pair: str, count: int) -> list[Candle]:
        idx = min(self._fetch_calls, len(self._responses) - 1)
        self._fetch_calls += 1
        if self._fetch_calls == 1:
            self._running = False
        return self._responses[idx][-count:]

    async def get_account_status(self) -> AccountStatus:
        raise NotImplementedError

    async def place_order(self, order: TradeOrder) -> TradeResult:
        raise NotImplementedError

    async def modify_position(
        self,
        position_id: str,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> TradeResult:
        raise NotImplementedError

    async def close_position(self, position_id: str, units: int | None = None) -> TradeResult:
        raise NotImplementedError

    async def get_open_positions(self) -> list[Position]:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_initial_seed_publishes_updates_without_agent_trigger(
    monkeypatch: pytest.MonkeyPatch,
):
    event_bus = EventBus()
    update_messages = []
    trigger_messages = []

    async def _capture_update(message):
        update_messages.append(message)

    async def _capture_trigger(message):
        trigger_messages.append(message)

    event_bus.subscribe(EventType.M5_CANDLE_UPDATE, _capture_update)
    event_bus.subscribe(EventType.M5_CANDLE_TRIGGER, _capture_trigger)

    initial = [
        _make_m5_candle(datetime(2026, 5, 6, 6, 20, tzinfo=UTC), "1.1000"),
        _make_m5_candle(datetime(2026, 5, 6, 6, 25, tzinfo=UTC), "1.1005"),
        _make_m5_candle(datetime(2026, 5, 6, 6, 30, tzinfo=UTC), "1.1010"),
    ]

    broker = TriggerPublishingBroker([initial])
    broker._running = True

    monkeypatch.setattr(
        broker,
        "_expected_latest_m5_open",
        staticmethod(lambda now=None: datetime(2026, 5, 6, 6, 25, tzinfo=UTC)),
    )

    await broker._m5_loop(
        "EURUSD",
        event_bus,
        poll_interval_seconds=0,
        lookback_count=3,
        agent_trigger_delay_seconds=0,
    )
    await event_bus.flush()

    assert [msg.payload["candle"]["timestamp"] for msg in update_messages] == [
        "2026-05-06T06:20:00Z",
        "2026-05-06T06:25:00Z",
    ]
    assert trigger_messages == []


@pytest.mark.asyncio
async def test_second_candle_change_publishes_updates_and_delayed_agent_trigger(
    monkeypatch: pytest.MonkeyPatch,
):
    event_bus = EventBus()
    update_messages = []
    trigger_messages = []

    async def _capture_update(message):
        update_messages.append(message)

    async def _capture_trigger(message):
        trigger_messages.append(message)

    event_bus.subscribe(EventType.M5_CANDLE_UPDATE, _capture_update)
    event_bus.subscribe(EventType.M5_CANDLE_TRIGGER, _capture_trigger)

    initial = [
        _make_m5_candle(datetime(2026, 5, 6, 6, 20, tzinfo=UTC), "1.1000"),
        _make_m5_candle(datetime(2026, 5, 6, 6, 25, tzinfo=UTC), "1.1005"),
        _make_m5_candle(datetime(2026, 5, 6, 6, 30, tzinfo=UTC), "1.1010"),
    ]
    refreshed = [
        _make_m5_candle(datetime(2026, 5, 6, 6, 20, tzinfo=UTC), "1.1000"),
        _make_m5_candle(datetime(2026, 5, 6, 6, 25, tzinfo=UTC), "1.1005"),
        _make_m5_candle(datetime(2026, 5, 6, 6, 30, tzinfo=UTC), "1.1018"),
    ]

    broker = TriggerPublishingBroker([initial, refreshed])
    broker._running = True
    broker._last_m5_time_by_pair["EURUSD"] = datetime(2026, 5, 6, 6, 20, tzinfo=UTC)

    monkeypatch.setattr(
        broker,
        "_expected_latest_m5_open",
        staticmethod(lambda now=None: datetime(2026, 5, 6, 6, 25, tzinfo=UTC)),
    )

    await broker._m5_loop(
        "EURUSD",
        event_bus,
        poll_interval_seconds=0,
        lookback_count=3,
        agent_trigger_delay_seconds=0,
    )
    delayed_task = broker._agent_trigger_tasks_by_pair.get("EURUSD")
    if delayed_task is not None:
        await delayed_task
    await event_bus.flush()

    update_timestamps = [msg.payload["candle"]["timestamp"] for msg in update_messages]
    assert update_timestamps == [
        "2026-05-06T06:20:00Z",
        "2026-05-06T06:25:00Z",
        "2026-05-06T06:30:00Z",
    ]
    assert update_messages[-1].payload["candle"]["close"] == "1.1018"

    assert len(trigger_messages) == 1
    assert trigger_messages[0].payload["candle"]["timestamp"] == "2026-05-06T06:30:00Z"
    assert trigger_messages[0].payload["candle"]["close"] == "1.1018"
