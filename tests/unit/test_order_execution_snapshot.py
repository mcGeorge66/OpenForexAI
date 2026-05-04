from __future__ import annotations

from openforexai.tools.base import ToolContext
from openforexai.tools.trading.order_execution import _build_market_context_snapshot


def test_build_market_context_snapshot_preserves_full_analysis_and_extracts_overlays() -> None:
    analysis_text = """
{
  "symbol": "EURUSD",
  "decision": "BIAS_SHORT",
  "confidence": 0.68,
  "order_start_signal": "YES",
  "entry_quality": "MARGINAL",
  "setup_type": "PULLBACK_ENTRY",
  "analysis_summary": "Bearish continuation with moderate volatility.",
  "trend_assessment": "H1 EMA20 (1.16923) is below EMA50 (1.17014) and both slope down.",
  "momentum_assessment": "H1 RSI(7) = 36.4 and still below 50.",
  "volatility_assessment": "H1 ATR(7) = 0.001447 with enough movement potential.",
  "support_resistance_assessment": "Nearest relevant support below: 1.16665. Nearest resistance above: 1.16795.",
  "invalidation_level": 1.169084,
  "first_target": 1.1661,
  "conflict_flags": ["m5_retracement"]
}
""".strip()

    context = ToolContext(
        agent_id="OXS_T-ALL___-BA-ANLYS",
        broker_name="OXS_T",
        pair="EURUSD",
        extra={
            "analysis_response_text": analysis_text,
            "analysis_source_agent_id": "OXS_T-EURUSD-AA-ANLYS",
        },
    )

    snapshot = _build_market_context_snapshot(
        arguments={"risk_pct": 1.0},
        context=context,
        direction_value="SELL",
        order_type_value="MARKET",
    )

    assert snapshot["analyst_recommendation_raw"] == analysis_text
    assert snapshot["analysis_source_agent_id"] == "OXS_T-EURUSD-AA-ANLYS"
    assert snapshot["analyst_recommendation"]["symbol"] == "EURUSD"
    assert snapshot["decision_context"]["decision"] == "BIAS_SHORT"
    assert snapshot["analysis_overlays"]["levels"]["support"] == [1.16665]
    assert snapshot["analysis_overlays"]["levels"]["resistance"] == [1.16795]
    assert snapshot["analysis_overlays"]["levels"]["invalidation"] == [1.169084]
    assert snapshot["analysis_overlays"]["levels"]["target"] == [1.1661]
    indicator_map = {
        indicator["name"]: indicator["value"]
        for indicator in snapshot["analysis_overlays"]["indicators"]
    }
    assert indicator_map["EMA20"] == 1.16923
    assert indicator_map["EMA50"] == 1.17014
    assert indicator_map["RSI7"] == 36.4
    assert indicator_map["ATR7"] == 0.001447
