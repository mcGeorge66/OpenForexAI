"""Demo LLM provider template.

Shows how to implement AbstractLLMProvider and return canonical response types.
"""
from __future__ import annotations

from typing import Any

from openforexai.ports.llm import (
    AbstractLLMProvider,
    LLMResponse,
    LLMResponseWithTools,
    ToolCall,
    ToolSpec,
)


class DemoLLMProvider(AbstractLLMProvider):
    def __init__(self, model: str = "demo-llm-v1") -> None:
        self._model = model

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "DemoLLMProvider":
        model = str(cfg.get("model", "demo-llm-v1"))
        return cls(model=model)

    @property
    def model_id(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        content = f"[demo:{self._model}] {user_message}"
        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=len(system_prompt) + len(user_message),
            output_tokens=len(content),
            raw={"provider": "demo"},
        )

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type,
    ) -> dict[str, Any]:
        # Real providers would parse/validate against response_schema.
        return {"status": "ok", "model": self._model, "message": user_message}

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponseWithTools:
        last_text = str(messages[-1].get("content", "")) if messages else ""
        if tools and "call_tool" in last_text.lower():
            call = ToolCall(id="demo-call-1", name=tools[0]["name"], arguments={})
            return LLMResponseWithTools(
                content=None,
                tool_calls=[call],
                stop_reason="tool_use",
                model=self._model,
                input_tokens=20,
                output_tokens=5,
                raw={"provider": "demo", "mode": "tool_use"},
            )
        return LLMResponseWithTools(
            content=f"[demo:{self._model}] {last_text}",
            tool_calls=[],
            stop_reason="end_turn",
            model=self._model,
            input_tokens=20,
            output_tokens=10,
            raw={"provider": "demo", "mode": "text"},
        )

