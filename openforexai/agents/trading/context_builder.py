from __future__ import annotations

from decimal import Decimal

from openforexai.models.analysis import AnalysisResult
from openforexai.models.market import Candle, MarketSnapshot
from openforexai.models.trade import TradeResult

# Maps config key → MarketSnapshot attribute name
_SNAPSHOT_CANDLE_ATTR: dict[str, str] = {
    "M5": "candles_m5",
    "M15": "candles_m15",
    "M30": "candles_m30",
    "H1": "candles_h1",
    "H4": "candles_h4",
    "D1": "candles_d1",
}

# Default context shown when no context_candles config is provided
_DEFAULT_CONTEXT_CANDLES: dict[str, int] = {"M5": 20, "M15": 12, "H1": 5}


def build_trading_context(
    snapshot: MarketSnapshot,
    recent_trades: list[TradeResult],
    open_positions_count: int,
    account_balance: float,
    analysis: AnalysisResult | None = None,
    context_candles: dict[str, int] | None = None,
    extra_candles: dict[str, list[Candle]] | None = None,
    extra_indicators: dict[str, str] | None = None,
) -> str:
    """Assemble the user message for the TradingAgent LLM call.

    Args:
        context_candles:   mapping of timeframe → count to include from the snapshot.
                           Defaults to M5:20 / M15:12 / H1:5.
        extra_candles:     additional candles requested on-demand by the LLM in a
                           previous turn, keyed as "<PAIR>_<TF>" (e.g. "USDJPY_M5").
        extra_indicators:  on-demand indicator results, keyed as
                           "ATR(14,M15,USDJPY)" → "0.001234".
    """
    candle_cfg = context_candles if context_candles is not None else _DEFAULT_CONTEXT_CANDLES

    lines: list[str] = [
        f"=== Market Data: {snapshot.pair} ===",
        f"Snapshot time : {snapshot.snapshot_time.isoformat()}",
        f"Session       : {snapshot.session}",
        f"Current price : bid={snapshot.current_tick.bid}  ask={snapshot.current_tick.ask}",
    ]

    # ── Candle sections (driven by config) ───────────────────────────────────
    for tf, count in candle_cfg.items():
        attr = _SNAPSHOT_CANDLE_ATTR.get(tf)
        if attr is None:
            continue
        candles: list[Candle] = getattr(snapshot, attr, [])
        if not candles:
            continue
        lines += ["", f"--- Last {count} {tf} candles ---"]
        for c in candles[-count:]:
            lines.append(
                f"  {c.timestamp.strftime('%Y-%m-%d %H:%M')}  "
                f"O={c.open}  H={c.high}  L={c.low}  C={c.close}"
            )

    # ── On-demand extra candles (requested by LLM in previous turn) ──────────
    if extra_candles:
        for key, candles in extra_candles.items():
            if not candles:
                continue
            # key format: "<PAIR>_<TF>"  e.g. "USDJPY_M5"
            parts = key.rsplit("_", 1)
            label = f"{parts[0]} {parts[1]}" if len(parts) == 2 else key
            lines += ["", f"--- Requested candles: {label} ({len(candles)} bars) ---"]
            for c in candles:
                lines.append(
                    f"  {c.timestamp.strftime('%Y-%m-%d %H:%M')}  "
                    f"O={c.open}  H={c.high}  L={c.low}  C={c.close}"
                )

    # ── On-demand indicators (requested by LLM in previous turn) ─────────────
    if extra_indicators:
        lines += ["", "--- Requested indicators ---"]
        for name, value in extra_indicators.items():
            lines.append(f"  {name}: {value}")

    # ── Account context ───────────────────────────────────────────────────────
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

    # ── Technical analysis (if available) ────────────────────────────────────
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
                lines.append(
                    f"  [{p.timeframe}] {p.name} "
                    f"({p.direction.value}, reliability={p.reliability:.2f})"
                )
        if analysis.support_resistance:
            lines += ["", "Key S/R levels:"]
            for sr in analysis.support_resistance:
                lines.append(
                    f"  {sr.level_type} @ {sr.price:.5f}  strength={sr.strength:.2f}"
                )

    return "\n".join(lines)
