from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    raw: dict[str, Any]


class AbstractLLMProvider(ABC):
    """Port: every LLM adapter must implement this contract."""

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...

    @abstractmethod
    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type,  # Pydantic model class
    ) -> dict[str, Any]: ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...
