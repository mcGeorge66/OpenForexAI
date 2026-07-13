from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
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
    market_snapshot: dict | None = None



