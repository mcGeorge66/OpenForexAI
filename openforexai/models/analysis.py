from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SignalDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ChartPattern(BaseModel):
    name: str  # head_and_shoulders | double_top | doji | engulfing | fibonacci_retracement
    timeframe: str
    direction: SignalDirection
    reliability: float = Field(ge=0.0, le=1.0)
    description: str


class SupportResistanceLevel(BaseModel):
    price: float
    level_type: str  # support | resistance
    strength: float = Field(ge=0.0, le=1.0)  # how often it has held
    timeframe: str


class TrendAssessment(BaseModel):
    timeframe: str
    direction: SignalDirection
    strength: float = Field(ge=0.0, le=1.0)
    description: str


class AnalysisRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pair: str
    requester_agent_id: str
    correlation_id: str
    snapshot: dict  # serialised MarketSnapshot
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pair: str
    correlation_id: str
    signal: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    timeframe_signals: dict[str, str]  # timeframe -> bullish|bearish|neutral
    chart_patterns: list[ChartPattern] = Field(default_factory=list)
    support_resistance: list[SupportResistanceLevel] = Field(default_factory=list)
    trend_assessments: list[TrendAssessment] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)

