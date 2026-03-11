from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    TRADING = "trading"
    TECHNICAL_ANALYSIS = "technical_analysis"
    SUPERVISOR = "supervisor"
    OPTIMIZATION = "optimization"


class AgentDecision(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    agent_role: AgentRole
    pair: str | None = None
    decision_type: str  # signal | approve | reject | analyze | optimize
    input_context: dict
    output: dict
    llm_model: str
    tokens_used: int
    latency_ms: float
    decided_at: datetime


class AgentContext(BaseModel):
    agent_id: str
    pair: str | None = None
    system_prompt: str
    market_snapshot: dict | None = None
    recent_trades: list[dict] = Field(default_factory=list)
    open_positions: list[dict] = Field(default_factory=list)
    account_balance: float = 0.0
    custom_context: dict = Field(default_factory=dict)


class AgentPerformance(BaseModel):
    agent_id: str
    pair: str | None = None
    win_rate: float
    avg_pnl: float
    total_trades: int
    sharpe_ratio: float | None = None
    max_drawdown: float
    period_days: int

