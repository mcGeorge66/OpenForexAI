"""Demo tests for broker adapter templates."""
from __future__ import annotations

import pytest

from template.broker.demo_broker_adapter import DemoBrokerAdapter


@pytest.mark.asyncio
async def test_demo_broker_connect_and_fetch():
    b = DemoBrokerAdapter(short_name="DEMO1", default_pair="EURUSD")
    await b.connect()
    candle = await b.fetch_latest_m5_candle("EURUSD")
    assert candle is not None
    assert candle.timeframe == "M5"


@pytest.mark.asyncio
async def test_demo_broker_account_status():
    b = DemoBrokerAdapter(short_name="DEMO1")
    await b.connect()
    status = await b.get_account_status()
    assert status.broker_name == "DEMO1"

