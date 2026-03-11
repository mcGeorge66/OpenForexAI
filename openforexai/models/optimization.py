from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TradePattern(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pair: str
    pattern_type: str  # entry_timing | sl_placement | session_bias | indicator_combo
    description: str
    frequency: int
    win_rate_when_present: float
    avg_pnl_when_present: float
    conditions: dict  # indicator thresholds, session, etc.
    detected_at: datetime
    sample_size: int


class PromptCandidate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pair: str
    version: int
    system_prompt: str
    rationale: str
    source_patterns: list[str] = Field(default_factory=list)  # UUIDs of TradePatterns
    is_active: bool = False
    created_at: datetime


class BacktestResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    prompt_candidate_id: str
    pair: str
    period_start: datetime
    period_end: datetime
    total_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    vs_baseline_pnl_delta: float  # positive = improvement over active prompt
    completed_at: datetime

