from __future__ import annotations

from decimal import Decimal

from openforexai.models.risk import CorrelationMatrix, RiskAssessment, RiskParameters
from openforexai.models.trade import Position, TradeSignal


class RiskEngine:
    """Stateless risk checker.  All methods are pure functions of their inputs."""

    def __init__(self, params: RiskParameters) -> None:
        self.params = params

    def assess(
        self,
        signal: TradeSignal,
        open_positions: list[Position],
        account_balance: float,
        daily_pnl: float,
        correlation_matrix: CorrelationMatrix | None,
    ) -> RiskAssessment:
        current_drawdown = self._drawdown_pct(open_positions, account_balance)
        current_exposure = self._exposure_pct(open_positions, account_balance)

        # ── Hard stops ───────────────────────────────────────────────────────
        if current_drawdown >= self.params.max_drawdown_pct:
            return RiskAssessment(
                approved=False,
                rejection_reason=f"Max drawdown reached: {current_drawdown:.1f}%",
                current_exposure_pct=current_exposure,
                current_drawdown_pct=current_drawdown,
                correlation_risk=0.0,
            )

        if daily_pnl <= -(self.params.max_daily_loss_pct / 100) * account_balance:
            return RiskAssessment(
                approved=False,
                rejection_reason="Daily loss limit reached",
                current_exposure_pct=current_exposure,
                current_drawdown_pct=current_drawdown,
                correlation_risk=0.0,
            )

        if len(open_positions) >= self.params.max_open_positions:
            return RiskAssessment(
                approved=False,
                rejection_reason=f"Max open positions ({self.params.max_open_positions}) reached",
                current_exposure_pct=current_exposure,
                current_drawdown_pct=current_drawdown,
                correlation_risk=0.0,
            )

        # ── Position sizing ───────────────────────────────────────────────────
        risk_pips = abs(float(signal.entry_price - signal.stop_loss))
        units = self._calculate_units(
            account_balance=account_balance,
            risk_pct=self.params.max_risk_per_trade_pct,
            risk_pips=risk_pips,
            pair=signal.pair,
        )

        # ── Exposure check after adding this trade ────────────────────────────
        projected_exposure = current_exposure + self.params.max_risk_per_trade_pct
        if projected_exposure > self.params.max_total_exposure_pct:
            return RiskAssessment(
                approved=False,
                rejection_reason=f"Would exceed max exposure: {projected_exposure:.1f}%",
                current_exposure_pct=current_exposure,
                current_drawdown_pct=current_drawdown,
                correlation_risk=0.0,
            )

        # ── Correlation check ─────────────────────────────────────────────────
        correlation_risk = 0.0
        if correlation_matrix:
            open_pairs = [p.pair for p in open_positions]
            correlation_risk = self._max_correlation(
                signal.pair, open_pairs, correlation_matrix
            )
            if correlation_risk > self.params.max_correlation_threshold:
                return RiskAssessment(
                    approved=False,
                    rejection_reason=(
                        f"Pair {signal.pair} too correlated with open position "
                        f"(corr={correlation_risk:.2f})"
                    ),
                    current_exposure_pct=current_exposure,
                    current_drawdown_pct=current_drawdown,
                    correlation_risk=correlation_risk,
                )

        return RiskAssessment(
            approved=True,
            adjusted_units=units,
            current_exposure_pct=current_exposure,
            current_drawdown_pct=current_drawdown,
            correlation_risk=correlation_risk,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _drawdown_pct(positions: list[Position], balance: float) -> float:
        if balance <= 0:
            return 0.0
        total_unrealized = sum(float(p.unrealized_pnl) for p in positions if p.unrealized_pnl < 0)
        return abs(total_unrealized) / balance * 100

    @staticmethod
    def _exposure_pct(positions: list[Position], balance: float) -> float:
        if balance <= 0:
            return 0.0
        # Rough approximation: each open position = 1% risk
        return len(positions) * 1.0

    @staticmethod
    def _calculate_units(
        account_balance: float,
        risk_pct: float,
        risk_pips: float,
        pair: str,
    ) -> int:
        if risk_pips <= 0:
            return 0
        risk_amount = account_balance * (risk_pct / 100)
        from openforexai.data.normalizer import pip_size
        pip = float(pip_size(pair))
        units = int(risk_amount / (risk_pips * pip))
        return max(units, 0)

    @staticmethod
    def _max_correlation(
        pair: str,
        open_pairs: list[str],
        matrix: CorrelationMatrix,
    ) -> float:
        if not open_pairs:
            return 0.0
        corrs = [
            abs(matrix.matrix.get(pair, {}).get(op, 0.0))
            for op in open_pairs
            if op != pair
        ]
        return max(corrs) if corrs else 0.0

