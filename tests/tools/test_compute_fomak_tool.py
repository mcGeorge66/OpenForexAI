from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from openforexai.tools.base import ToolContext
from openforexai.tools.market.compute_fomak import ComputeFomakTool


def _context() -> ToolContext:
    return ToolContext(agent_id="a", broker_name="mt5_oxs_t", pair="EURUSD")


def _synthetic_candles(n: int, minutes: int) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    out = []
    price = 1.1000
    for i in range(n):
        price += 0.0006
        out.append({
            "timestamp": (start + timedelta(minutes=minutes * i)).isoformat(),
            "open": str(price - 0.0006), "high": str(price + 0.0002),
            "low": str(price - 0.0008), "close": str(price),
        })
    return out


@pytest.fixture
def tool() -> ComputeFomakTool:
    return ComputeFomakTool()


@pytest.fixture
def fake_bus_request(monkeypatch):
    """Serves enough M5 candles for lookback+warmup, and enough M15 candles for
    the higher-timeframe EMA — mirrors what DataContainer would actually return."""
    calls: list[dict] = []

    async def _fake(context, event_type, target_id, payload, instrument=None):
        calls.append({"payload": payload, "instrument": instrument})
        timeframe = payload["timeframe"]
        limit = payload["limit"]
        minutes = 5 if timeframe == "M5" else 15
        return {"candles": _synthetic_candles(limit, minutes), "error": None}

    monkeypatch.setattr("openforexai.tools.market.compute_fomak.bus_request", _fake)
    return calls


@pytest.mark.asyncio
async def test_returns_only_fomak_code_by_default(tool, fake_bus_request):
    result = await tool.execute({"timeframe": "M5", "lookback_candles": 24}, _context())
    assert "fomak" in result
    assert len(result["fomak"]) == 7
    assert "raw_values" not in result
    assert "explanation" not in result
    assert result["higher_timeframe"] == "M15"  # auto next-higher


@pytest.mark.asyncio
async def test_include_raw_values(tool, fake_bus_request):
    result = await tool.execute(
        {"timeframe": "M5", "lookback_candles": 24, "include_raw_values": True}, _context(),
    )
    assert "raw_values" in result
    assert "strength" in result["raw_values"]
    assert result["direction"] in ("U", "D", "N")


@pytest.mark.asyncio
async def test_include_explanation(tool, fake_bus_request):
    result = await tool.execute(
        {"timeframe": "M5", "lookback_candles": 24, "include_explanation": True, "lang": "de"}, _context(),
    )
    assert "explanation" in result
    assert result["fomak"] in result["explanation"]


@pytest.mark.asyncio
async def test_explicit_higher_timeframe_overrides_auto(tool, fake_bus_request):
    await tool.execute(
        {"timeframe": "M5", "lookback_candles": 24, "higher_timeframe": "H1"}, _context(),
    )
    higher_tf_calls = [c for c in fake_bus_request if c["payload"]["timeframe"] == "H1"]
    assert len(higher_tf_calls) == 1


@pytest.mark.asyncio
async def test_anchor_passed_through_to_both_fetches(tool, fake_bus_request):
    anchor = "2026-01-05T00:00:00+00:00"
    await tool.execute({"timeframe": "M5", "lookback_candles": 24, "anchor": anchor}, _context())
    assert all(c["payload"].get("start") == anchor for c in fake_bus_request)


@pytest.mark.asyncio
async def test_invalid_timeframe_rejected(tool, fake_bus_request):
    result = await tool.execute({"timeframe": "M1", "lookback_candles": 24}, _context())
    assert "error" in result
    assert fake_bus_request == []


@pytest.mark.asyncio
async def test_missing_lookback_candles_rejected(tool, fake_bus_request):
    result = await tool.execute({"timeframe": "M5"}, _context())
    assert "error" in result
    assert fake_bus_request == []


@pytest.mark.asyncio
async def test_no_pair_available_rejected(tool, fake_bus_request):
    context = ToolContext(agent_id="a", broker_name="mt5_oxs_t", pair=None)
    result = await tool.execute({"timeframe": "M5", "lookback_candles": 24}, context)
    assert "error" in result
    assert fake_bus_request == []


@pytest.mark.asyncio
async def test_insufficient_candle_history_reported_clearly(tool, monkeypatch):
    async def _fake_short(context, event_type, target_id, payload, instrument=None):
        return {"candles": _synthetic_candles(5, 5), "error": None}  # far fewer than needed

    monkeypatch.setattr("openforexai.tools.market.compute_fomak.bus_request", _fake_short)
    result = await tool.execute({"timeframe": "M5", "lookback_candles": 24}, _context())
    assert "error" in result
    assert "history" in result["error"].lower()


@pytest.mark.asyncio
async def test_data_container_error_propagated(tool, monkeypatch):
    async def _fake_error(context, event_type, target_id, payload, instrument=None):
        return {"candles": [], "error": "boom"}

    monkeypatch.setattr("openforexai.tools.market.compute_fomak.bus_request", _fake_error)
    result = await tool.execute({"timeframe": "M5", "lookback_candles": 24}, _context())
    assert "error" in result
    assert "boom" in result["error"]
