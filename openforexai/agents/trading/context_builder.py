from __future__ import annotations

import json
from decimal import Decimal

from openforexai.models.analysis import AnalysisResult
from openforexai.models.market import MarketSnapshot
from openforexai.models.trade import TradeResult


def build_trading_context(
    snapshot: MarketSnapshot,
    recent_trades: list[TradeResult],
    open_positions_count: int,
    account_balance: float,
    analysis: AnalysisResult | None = None,
) -> str:
    """Assemble the user message for the TradingAgent LLM call."""
    lines: list[str] = [
        f"=== Market Data: {snapshot.pair} ===",
        f"Snapshot time : {snapshot.snapshot_time.isoformat()}",
        f"Session       : {snapshot.session}",
        f"Current price : bid={snapshot.current_tick.bid}  ask={snapshot.current_tick.ask}",
        "",
        "--- H1 Indicators ---",
    ]
    for name, value in snapshot.indicators.items():
        lines.append(f"  {name}: {round(value, 5)}")

    lines += [
        "",
        f"--- Last 5 H1 candles ---",
    ]
    for c in snapshot.candles_h1[-5:]:
        lines.append(
            f"  {c.timestamp.strftime('%Y-%m-%d %H:%M')}  "
            f"O={c.open}  H={c.high}  L={c.low}  C={c.close}"
        )

    lines += [
        "",
        "=== Account Context ===",
        f"Balance         : {account_balance:.2f}",
        f"Open positions  : {open_positions_count}",
    ]

    if recent_trades:
        lines += ["", "--- Recent closed trades (last 5) ---"]
        for t in recent_trades[-5:]:
            outcome = "win" if (t.pnl or Decimal(0)) > 0 else "loss"
            lines.append(
                f"  {t.order.signal.direction.value}  "
                f"pnl={t.pnl}  reason={t.close_reason}  [{outcome}]"
            )

    if analysis:
        lines += [
            "",
            "=== Technical Analysis Result ===",
            f"Signal     : {analysis.signal.value}",
            f"Confidence : {analysis.confidence:.2f}",
            f"Reasoning  : {analysis.reasoning}",
            "",
            "Timeframe signals:",
        ]
        for tf, sig in analysis.timeframe_signals.items():
            lines.append(f"  {tf}: {sig}")
        if analysis.chart_patterns:
            lines += ["", "Chart patterns detected:"]
            for p in analysis.chart_patterns:
                lines.append(f"  [{p.timeframe}] {p.name} ({p.direction.value}, reliability={p.reliability:.2f})")
        if analysis.support_resistance:
            lines += ["", "Key S/R levels:"]
            for sr in analysis.support_resistance:
                lines.append(f"  {sr.level_type} @ {sr.price:.5f}  strength={sr.strength:.2f}")

    return "\n".join(lines)
