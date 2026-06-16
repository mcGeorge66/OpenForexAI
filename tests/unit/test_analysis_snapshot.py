from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json

import pytest

from openforexai.agents.analysis_snapshot import (
    DEFAULT_CANDLE_TRANSFORM_SCRIPT,
    DEFAULT_INDICATOR_TRANSFORM_SCRIPT,
    build_analysis_snapshot,
    build_decision_only_system_prompt,
    build_decision_only_user_message,
    preview_snapshot_tool_block,
)
from openforexai.models.market import Candle
from openforexai.tools.base import ToolContext
from openforexai.tools.market.calculate_indicator import CalculateIndicatorTool


def _make_candle(ts: datetime, open_price: float, high: float, low: float, close: float, timeframe: str) -> Candle:
    return Candle(
        timestamp=ts,
        open=Decimal(str(open_price)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        tick_volume=100,
        spread=Decimal("10"),
        timeframe=timeframe,
    )


class _StubDataContainer:
    def __init__(self, m5: list[Candle], h1: list[Candle]) -> None:
        self._m5 = m5
        self._h1 = h1

    async def get_candles(self, broker_name: str, pair: str, timeframe: str, limit: int | None = None) -> list[Candle]:
        candles = self._m5 if timeframe == "M5" else self._h1
        return candles[-limit:] if limit is not None else candles


class _RecordingStubDataContainer:
    """Stub that records which timeframes were requested to ``get_candles``."""

    def __init__(self, m5: list[Candle], h1: list[Candle]) -> None:
        self._m5 = m5
        self._h1 = h1
        self.requested_timeframes: list[str] = []

    async def get_candles(self, broker_name: str, pair: str, timeframe: str, limit: int | None = None) -> list[Candle]:
        self.requested_timeframes.append(timeframe)
        candles = self._m5 if timeframe == "M5" else self._h1
        return candles[-limit:] if limit is not None else candles


def _payload_from_message(message: str) -> dict[str, object]:
    _prefix, payload = message.split("\n\n", 1)
    return json.loads(payload)


# =============================================================================
# Tool block execution
# =============================================================================

@pytest.mark.asyncio
async def test_build_analysis_snapshot_uses_tool_blocks_and_keeps_extra_outputs() -> None:
    start = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    m5 = [_make_candle(start + timedelta(minutes=5 * i), 1.17, 1.171, 1.169, 1.1705 + (i * 0.00001), "M5") for i in range(30)]
    h1 = [_make_candle(start + timedelta(hours=i), 1.16, 1.161, 1.159, 1.1605 + (i * 0.00002), "H1") for i in range(140)]

    snapshot, errors = await build_analysis_snapshot(
        data_container=_StubDataContainer(m5, h1),  # type: ignore[arg-type]
        broker_name="OXS_T",
        pair="EURUSD",
        trigger_payload={"candle": {"timestamp": "2026-05-07T11:35:00Z", "close": "1.17050"}},
        profile={
            "name": "tool_profile",
            "tool_blocks": [
                {"id": "m5_recent",   "tool_name": "get_candles",         "output_key": "m5_recent",   "enabled": True, "arguments": {"timeframe": "M5", "count": 18}},
                {"id": "h1_recent",   "tool_name": "get_candles",         "output_key": "h1_recent",   "enabled": True, "arguments": {"timeframe": "H1", "count": 90}},
                {"id": "ema_fast",    "tool_name": "calculate_indicator", "output_key": "ema_fast",    "enabled": True, "arguments": {"indicator": "EMA", "period": 20, "timeframe": "H1", "history": 3}},
                {"id": "ema_slow",    "tool_name": "calculate_indicator", "output_key": "ema_slow",    "enabled": True, "arguments": {"indicator": "EMA", "period": 50, "timeframe": "H1", "history": 3}},
                {"id": "rsi_primary", "tool_name": "calculate_indicator", "output_key": "rsi_primary", "enabled": True, "arguments": {"indicator": "RSI", "period": 5,  "timeframe": "H1", "history": 3}},
                {"id": "atr_primary", "tool_name": "calculate_indicator", "output_key": "atr_primary", "enabled": True, "arguments": {"indicator": "ATR", "period": 10, "timeframe": "H1", "history": 3}},
                {"id": "m5_extra",    "tool_name": "get_candles",         "output_key": "m5_extra_preview", "enabled": True, "arguments": {"timeframe": "M5", "count": 2}},
            ],
        },
    )

    assert errors == []
    assert snapshot["snapshot_profile_name"] == "tool_profile"

    # tool_outputs is always written and contains every block's transformed result
    assert "tool_outputs" in snapshot
    assert len(snapshot["tool_outputs"]["m5_extra_preview"]) == 2
    for key in ("m5_recent", "h1_recent", "ema_fast", "rsi_primary", "atr_primary"):
        assert key in snapshot["tool_outputs"], f"Expected {key!r} in tool_outputs"

    # tool_blocks summary lists every executed block
    block_ids = {b["id"] for b in snapshot["tool_blocks"]}
    assert {"m5_extra", "ema_fast", "rsi_primary"} <= block_ids


# =============================================================================
# System prompt helpers
# =============================================================================

def test_build_decision_only_system_prompt_uses_profile_override_modes() -> None:
    replaced = build_decision_only_system_prompt(
        "BASE",
        {"prompt": "PROFILE", "mode": "replace"},
    )
    appended = build_decision_only_system_prompt(
        "BASE",
        {"prompt": "PROFILE", "mode": "append"},
    )

    assert replaced.startswith("PROFILE")
    assert "BASE" not in replaced.split("RUNTIME OVERRIDE", 1)[0]
    assert appended.startswith("BASE")
    assert "PROFILE" in appended


# =============================================================================
# Assembly transform / user message
# =============================================================================

@pytest.mark.asyncio
async def test_build_decision_only_user_message_contains_assembled_payload_not_pipeline_metadata() -> None:
    """The assembly transform script builds the payload; pipeline metadata is excluded."""
    start = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    m5 = [
        _make_candle(start + timedelta(minutes=5 * i), 1.1700 + (i * 0.0001), 1.1702 + (i * 0.0001), 1.1698 + (i * 0.0001), 1.1701 + (i * 0.0001), "M5")
        for i in range(20)
    ]
    h1 = [
        _make_candle(start + timedelta(hours=i), 1.1600 + (i * 0.0002), 1.1605 + (i * 0.0002), 1.1595 + (i * 0.0002), 1.1603 + (i * 0.0002), "H1")
        for i in range(120)
    ]

    # Assembly script explicitly builds the result; pipeline keys are omitted.
    assembly_script = """\
result = {
    "symbol": snapshot.get("symbol"),
    "price": snapshot.get("latest_price"),
    "trigger": snapshot.get("trigger_candle"),
    "m5_candles": tool_outputs.get("m5_recent"),
    "h1_candles": tool_outputs.get("h1_recent"),
    "ema_fast": tool_outputs.get("ema_fast"),
    "rsi": tool_outputs.get("rsi_primary"),
}
"""
    profile = {
        "name": "assembly_test_profile",
        "decision_input_prefix": "PREFIX LINE",
        "tool_blocks": [
            {"id": "m5_recent",   "tool_name": "get_candles",         "output_key": "m5_recent",   "enabled": True, "transform_script": DEFAULT_CANDLE_TRANSFORM_SCRIPT,    "arguments": {"timeframe": "M5", "count": 20}},
            {"id": "h1_recent",   "tool_name": "get_candles",         "output_key": "h1_recent",   "enabled": True, "transform_script": DEFAULT_CANDLE_TRANSFORM_SCRIPT,    "arguments": {"timeframe": "H1", "count": 120}},
            {"id": "ema_fast",    "tool_name": "calculate_indicator", "output_key": "ema_fast",    "enabled": True, "transform_script": DEFAULT_INDICATOR_TRANSFORM_SCRIPT, "arguments": {"indicator": "EMA", "period": 20, "timeframe": "H1", "history": 3}},
            {"id": "rsi_primary", "tool_name": "calculate_indicator", "output_key": "rsi_primary", "enabled": True, "transform_script": DEFAULT_INDICATOR_TRANSFORM_SCRIPT, "arguments": {"indicator": "RSI", "period": 7,  "timeframe": "H1", "history": 3}},
        ],
        "assembly_transform_script": assembly_script,
    }

    snapshot, errors = await build_analysis_snapshot(
        data_container=_StubDataContainer(m5, h1),  # type: ignore[arg-type]
        broker_name="OXS_T",
        pair="EURUSD",
        trigger_payload={"candle": {"timestamp": "2026-05-07T11:35:00Z", "close": "1.17200", "spread": "10"}},
        profile=profile,
    )

    assert errors == []
    message = build_decision_only_user_message(snapshot, profile)
    assert message.startswith("PREFIX LINE")
    payload = _payload_from_message(message)

    # Fields explicitly written by the assembly script are present.
    assert "symbol" in payload
    assert "price" in payload
    assert "trigger" in payload
    assert "m5_candles" in payload
    assert "h1_candles" in payload
    assert "ema_fast" in payload
    assert "rsi" in payload

    # Pipeline metadata is excluded (assembly script did not include it).
    assert "tool_blocks" not in payload
    assert "snapshot_schema_version" not in payload
    assert "snapshot_profile_name" not in payload
    assert "broker_name" not in payload
    assert "tool_outputs" not in payload


# =============================================================================
# Tool block preview
# =============================================================================

@pytest.mark.asyncio
async def test_snapshot_tool_preview_returns_raw_and_transformed_outputs() -> None:
    start = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    m5 = [_make_candle(start + timedelta(minutes=5 * i), 1.17, 1.171, 1.169, 1.1705 + (i * 0.00001), "M5") for i in range(20)]
    h1 = [_make_candle(start + timedelta(hours=i), 1.16, 1.161, 1.159, 1.1605 + (i * 0.00002), "H1") for i in range(120)]

    preview = await preview_snapshot_tool_block(
        block={
            "id": "ema_fast",
            "tool_name": "calculate_indicator",
            "output_key": "ema_fast",
            "enabled": True,
            "transform_script": DEFAULT_INDICATOR_TRANSFORM_SCRIPT,
            "arguments": {"indicator": "EMA", "period": 20, "timeframe": "H1", "history": 3},
        },
        agent_id="OXS_T-EURUSD-AA-ANLYS",
        broker_name="OXS_T",
        pair="EURUSD",
        data_container=_StubDataContainer(m5, h1),  # type: ignore[arg-type]
    )

    assert preview["errors"] == []
    assert isinstance(preview["raw_output"], dict)
    assert isinstance(preview["transformed_output"], dict)
    assert preview["transformed_output"]["indicator"] == "EMA"
    assert preview["transformed_output"]["timeframe"] == "H1"
    assert "latest" in preview["transformed_output"]
    assert "values" in preview["transformed_output"]
    assert isinstance(preview["raw_output"]["values"], list)
    assert isinstance(preview["raw_output"]["values"][0], dict)
    assert "timestamp" in preview["raw_output"]["values"][0]
    assert "value" in preview["raw_output"]["values"][0]


# =============================================================================
# calculate_indicator tool
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("indicator,period", [("EMA", 20), ("RSI", 7), ("ATR", 7)])
async def test_calculate_indicator_tool_returns_timestamped_series(indicator: str, period: int) -> None:
    start = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    h1 = [
        _make_candle(start + timedelta(hours=i), 1.1600 + (i * 0.0002), 1.1605 + (i * 0.0002), 1.1595 + (i * 0.0002), 1.1603 + (i * 0.0002), "H1")
        for i in range(120)
    ]
    tool = CalculateIndicatorTool()
    result = await tool.execute(
        {"indicator": indicator, "period": period, "timeframe": "H1", "history": 3},
        ToolContext(
            agent_id="OXS_T-EURUSD-AA-ANLYS",
            broker_name="OXS_T",
            pair="EURUSD",
            data_container=_StubDataContainer([], h1),
        ),
    )

    assert result["indicator"] == indicator
    assert result["timeframe"] == "H1"
    assert result["history"] == 3
    assert isinstance(result["values"], list)
    assert len(result["values"]) == 3
    for item in result["values"]:
        assert isinstance(item, dict)
        assert isinstance(item.get("timestamp"), str)
        assert "value" in item


# =============================================================================
# SHORT_TF / LONG_TF placeholder resolution
# =============================================================================

@pytest.mark.asyncio
async def test_short_tf_long_tf_placeholders_are_resolved() -> None:
    """SHORT_TF and LONG_TF placeholder strings are replaced with the profile's
    short_timeframe / long_timeframe values before the tool is called."""
    start = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    m5 = [_make_candle(start + timedelta(minutes=5 * i), 1.17, 1.171, 1.169, 1.1705, "M5") for i in range(30)]
    h1 = [_make_candle(start + timedelta(hours=i), 1.16, 1.161, 1.159, 1.1605, "H1") for i in range(140)]
    dc = _RecordingStubDataContainer(m5, h1)

    snapshot, errors = await build_analysis_snapshot(
        data_container=dc,  # type: ignore[arg-type]
        broker_name="OXS_T",
        pair="EURUSD",
        trigger_payload={"candle": {"timestamp": "2026-05-07T11:35:00Z", "close": "1.17050"}},
        profile={
            "name": "tf_placeholder_test",
            "short_timeframe": "M15",
            "long_timeframe": "H4",
            "tool_blocks": [
                {"id": "short_candles", "tool_name": "get_candles", "output_key": "short_candles", "enabled": True, "arguments": {"timeframe": "SHORT_TF", "count": 10}},
                {"id": "long_candles",  "tool_name": "get_candles", "output_key": "long_candles",  "enabled": True, "arguments": {"timeframe": "LONG_TF",  "count": 10}},
            ],
        },
    )

    # Arguments stored in tool_blocks reflect the resolved (not placeholder) timeframe.
    blocks_by_id = {b["id"]: b for b in snapshot["tool_blocks"]}
    assert blocks_by_id["short_candles"]["arguments"]["timeframe"] == "M15"
    assert blocks_by_id["long_candles"]["arguments"]["timeframe"] == "H4"

    # The data container received the resolved timeframe strings, never the placeholders.
    assert "M15" in dc.requested_timeframes
    assert "H4" in dc.requested_timeframes
    assert "SHORT_TF" not in dc.requested_timeframes
    assert "LONG_TF" not in dc.requested_timeframes


# =============================================================================
# Script calculation block
# =============================================================================

@pytest.mark.asyncio
async def test_script_calculation_block_runs_and_returns_dict() -> None:
    """A calculation block of type 'script' executes free-form Python with access
    to all transformed tool outputs and writes its result to ``result``."""
    start = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)
    m5 = [_make_candle(start + timedelta(minutes=5 * i), 1.17, 1.171, 1.169, 1.1705 + (i * 0.00001), "M5") for i in range(20)]
    h1 = [_make_candle(start + timedelta(hours=i), 1.16, 1.161, 1.159, 1.1605, "H1") for i in range(50)]

    script_code = """\
candles = tool_outputs.get("m5_data") or []
result = {
    "candle_count": len(candles),
    "last_close": candles[-1]["close"] if candles else None,
    "custom_label": "script_ran",
}
"""

    snapshot, errors = await build_analysis_snapshot(
        data_container=_StubDataContainer(m5, h1),  # type: ignore[arg-type]
        broker_name="OXS_T",
        pair="EURUSD",
        trigger_payload={"candle": {"timestamp": "2026-05-07T11:35:00Z", "close": "1.17050"}},
        profile={
            "name": "script_calc_test",
            "tool_blocks": [
                {"id": "m5_data", "tool_name": "get_candles", "output_key": "m5_data", "enabled": True,
                 "transform_script": DEFAULT_CANDLE_TRANSFORM_SCRIPT, "arguments": {"timeframe": "M5", "count": 15}},
            ],
            "calculation_blocks": [
                {"id": "custom_script", "type": "script", "enabled": True, "script": script_code},
            ],
        },
    )

    assert errors == []
    assert "calculations" in snapshot

    # Script blocks are always grouped under "global".
    calc_result = snapshot["calculations"]["global"]["custom_script"]
    assert calc_result["custom_label"] == "script_ran"
    assert calc_result["candle_count"] == 15
    assert calc_result["last_close"] is not None
