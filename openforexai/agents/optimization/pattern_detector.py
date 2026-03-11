from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from openforexai.models.optimization import TradePattern
from openforexai.models.trade import TradeResult


def detect_patterns(trades: list[TradeResult]) -> list[TradePattern]:
    """Analyse a list of closed trades and surface recurring patterns."""
    if len(trades) < 5:
        return []

    patterns: list[TradePattern] = []

    # ── Session bias ──────────────────────────────────────────────────────────
    session_stats: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.pnl is not None and t.opened_at is not None:
            hour = t.opened_at.hour
            session = _hour_to_session(hour)
            session_stats[session].append(float(t.pnl))

    for session, pnls in session_stats.items():
        if len(pnls) < 3:
            continue
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls)
        avg_pnl = sum(pnls) / len(pnls)
        if win_rate >= 0.6 or win_rate <= 0.3:
            patterns.append(
                TradePattern(
                    pair=trades[0].order.signal.pair,
                    pattern_type="session_bias",
                    description=f"{'High' if win_rate >= 0.6 else 'Low'} win rate during {session} session",
                    frequency=len(pnls),
                    win_rate_when_present=win_rate,
                    avg_pnl_when_present=avg_pnl,
                    conditions={"session": session},
                    detected_at=datetime.now(timezone.utc),
                    sample_size=len(pnls),
                )
            )

    # ── Direction bias ────────────────────────────────────────────────────────
    direction_stats: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        if t.pnl is not None:
            direction_stats[t.order.signal.direction.value].append(float(t.pnl))

    for direction, pnls in direction_stats.items():
        if len(pnls) < 3:
            continue
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls)
        avg_pnl = sum(pnls) / len(pnls)
        if win_rate >= 0.65:
            patterns.append(
                TradePattern(
                    pair=trades[0].order.signal.pair,
                    pattern_type="direction_bias",
                    description=f"Strong {direction} win rate",
                    frequency=len(pnls),
                    win_rate_when_present=win_rate,
                    avg_pnl_when_present=avg_pnl,
                    conditions={"direction": direction},
                    detected_at=datetime.now(timezone.utc),
                    sample_size=len(pnls),
                )
            )

    return patterns


def _hour_to_session(hour: int) -> str:
    if 7 <= hour < 16:
        return "london"
    if 12 <= hour < 21:
        return "new_york"
    if 0 <= hour < 9:
        return "tokyo"
    return "sydney"

