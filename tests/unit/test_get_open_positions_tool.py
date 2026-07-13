from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from openforexai.tools.account.get_open_positions import GetOpenPositionsTool
from openforexai.tools.base import ToolContext


def _position(pair: str, position_id: str) -> dict[str, object]:
    return {
        "broker_position_id": position_id,
        "broker_name": "MT5__",
        "pair": pair,
        "direction": "BUY",
        "units": 1000,
        "open_price": Decimal("1.1000"),
        "current_price": Decimal("1.1010"),
        "stop_loss": Decimal("1.0950"),
        "take_profit": Decimal("1.1100"),
        "unrealized_pnl": Decimal("10.0"),
        "opened_at": datetime.now(UTC),
        "sync_key": None,
    }


async def test_get_open_positions_returns_metadata_without_pair_when_no_positions(monkeypatch) -> None:
    async def fake_bus_request(**kwargs):
        return {"positions": []}

    monkeypatch.setattr(
        "openforexai.tools.account.get_open_positions.bus_request",
        fake_bus_request,
    )

    tool = GetOpenPositionsTool()
    context = ToolContext(agent_id="TEST1-EURUSD-AA-TEST", broker_name="MT5__", pair="EURUSD")

    result = await tool.execute({}, context)

    assert result["success"] is True
    assert result["pair_filter"] is None
    assert result["used_context_pair"] == "EURUSD"
    assert result["total_count"] == 0
    assert result["pairs"] == {}


async def test_get_open_positions_returns_metadata_for_requested_pair_without_matches(monkeypatch) -> None:
    async def fake_bus_request(**kwargs):
        return {"positions": []}

    monkeypatch.setattr(
        "openforexai.tools.account.get_open_positions.bus_request",
        fake_bus_request,
    )

    tool = GetOpenPositionsTool()
    context = ToolContext(agent_id="TEST1-EURUSD-AA-TEST", broker_name="MT5__", pair="GBPUSD")

    result = await tool.execute({"pair": "GBPUSD"}, context)

    assert result["success"] is True
    assert result["pair_filter"] == "GBPUSD"
    assert result["used_context_pair"] == "GBPUSD"
    assert result["total_count"] == 0
    assert result["pairs"] == {"GBPUSD": {"count": 0, "orders": []}}


async def test_get_open_positions_groups_positions_by_pair(monkeypatch) -> None:
    async def fake_bus_request(**kwargs):
        return {
            "positions": [
                _position("EURUSD", "pos-1"),
                _position("USDJPY", "pos-2"),
                _position("EURUSD", "pos-3"),
            ]
        }

    monkeypatch.setattr(
        "openforexai.tools.account.get_open_positions.bus_request",
        fake_bus_request,
    )

    tool = GetOpenPositionsTool()
    context = ToolContext(agent_id="TEST1-EURUSD-AA-TEST", broker_name="MT5__", pair="EURUSD")

    result = await tool.execute({}, context)

    assert result["success"] is True
    assert result["broker_name"] == "MT5__"
    assert result["pair_filter"] is None
    assert result["used_context_pair"] == "EURUSD"
    assert result["total_count"] == 3
    assert result["pairs"]["EURUSD"]["count"] == 2
    assert result["pairs"]["USDJPY"]["count"] == 1
