from __future__ import annotations

from datetime import datetime, timezone

from openforexai.models.optimization import BacktestResult, PromptCandidate
from openforexai.models.trade import TradeResult


def backtest_prompt(
    candidate: PromptCandidate,
    historical_trades: list[TradeResult],
) -> BacktestResult:
    """Simple replay-based backtest.

    For each historical trade that was triggered during the backtest period,
    compute aggregate statistics.  In a production system this would re-run
    the LLM with the candidate prompt against historical snapshots; here we
    use the existing trade outcomes as a proxy.
    """
    if not historical_trades:
        return BacktestResult(
            prompt_candidate_id=str(candidate.id),
            pair=candidate.pair,
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            total_trades=0,
            win_rate=0.0,
            total_pnl=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            vs_baseline_pnl_delta=0.0,
            completed_at=datetime.now(timezone.utc),
        )

    pnls = [float(t.pnl or 0) for t in historical_trades]
    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / len(pnls) if pnls else 0.0
    total_pnl = sum(pnls)

    # Max drawdown
    peak, max_dd = 0.0, 0.0
    running = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualised, rough)
    import statistics

    if len(pnls) > 1 and statistics.stdev(pnls) > 0:
        sharpe = (sum(pnls) / len(pnls)) / statistics.stdev(pnls) * (252**0.5)
    else:
        sharpe = 0.0

    closed_times = [t.closed_at for t in historical_trades if t.closed_at]
    period_start = min(closed_times) if closed_times else datetime.now(timezone.utc)
    period_end = max(closed_times) if closed_times else datetime.now(timezone.utc)

    return BacktestResult(
        prompt_candidate_id=str(candidate.id),
        pair=candidate.pair,
        period_start=period_start,
        period_end=period_end,
        total_trades=len(pnls),
        win_rate=win_rate,
        total_pnl=total_pnl,
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        vs_baseline_pnl_delta=0.0,  # set by OptimizationAgent after comparing to baseline
        completed_at=datetime.now(timezone.utc),
    )

