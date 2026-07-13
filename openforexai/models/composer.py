from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ECToolCall(BaseModel):
    tool: str
    arguments: dict
    result: object | None = None
    success: bool = True
    error: str | None = None


class ECRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ec_id: str
    trigger: str
    input_json: dict = Field(default_factory=dict)
    config_snapshot: dict = Field(default_factory=dict)
    tool_calls: list[ECToolCall] = Field(default_factory=list)
    output_json: dict | None = None
    success: bool = True
    error: str | None = None
    latency_ms: float = 0.0
    run_at: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str | None = None
