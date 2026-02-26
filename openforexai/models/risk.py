from __future__ import annotations

from pydantic import BaseModel


class RiskParameters(BaseModel):
    max_risk_per_trade_pct: float = 1.0
    max_total_exposure_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    max_daily_loss_pct: float = 3.0
    max_correlation_threshold: float = 0.7
    max_open_positions: int = 6


class RiskAssessment(BaseModel):
    approved: bool
    rejection_reason: str | None = None
    adjusted_units: int | None = None
    current_exposure_pct: float
    current_drawdown_pct: float
    correlation_risk: float  # 0.0 = no risk, 1.0 = fully correlated


class CorrelationMatrix(BaseModel):
    pairs: list[str]
    matrix: dict[str, dict[str, float]]  # pair -> pair -> coefficient
    computed_at: str  # ISO datetime string
