from __future__ import annotations

import json
from typing import Any

import anthropic

from openforexai.adapters.llm.base import llm_retry
from openforexai.ports.llm import (
    AbstractLLMProvider,
    LLMResponse,
    LLMResponseWithTools,
    ToolCall,
    ToolSpec,
)


class AnthropicLLMProvider(AbstractLLMProvider):
    """Claude adapter using the native Anthropic SDK (tool_use API)."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-6",
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        default_temperature: float | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    @classmethod
    def from_config(cls, cfg: dict) -> "AnthropicLLMProvider":
        return cls(
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "claude-opus-4-6"),
            retry_attempts=cfg.get("retry_attempts", 3),
            retry_base_delay=cfg.get("retry_base_delay", 1.0),
            default_temperature=(
                cfg.get("temperature") if isinstance(cfg.get("temperature"), (int, float)) else None
            ),
            default_max_tokens=cfg.get("max_tokens", 4096),
        )

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def default_temperature(self) -> float | None:
        return self._default_temperature

    @property
    def default_max_tokens(self) -> int:
        return self._default_max_tokens

    # ── Simple completions ────────────────────────────────────────────────────

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens

        async def _call() -> LLMResponse:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": resolved_max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            msg = await self._client.messages.create(**kwargs)
            return LLMResponse(
                content=msg.content[0].text,
                model=msg.model,
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
                raw=msg.model_dump(),
            )

        return await llm_retry(_call, attempts=self._retry_attempts, base_delay=self._retry_base_delay)

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type,
    ) -> dict[str, Any]:
        schema = response_schema.model_json_schema()
        augmented_prompt = (
            f"{system_prompt}\n\nRespond ONLY with valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        response = await self.complete(
            system_prompt=augmented_prompt,
            user_message=user_message,
            temperature=0.0,
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)

    # ── Tool-use completions ──────────────────────────────────────────────────

    async def complete_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponseWithTools:
        """Single turn using Anthropic's native tool_use API.

        ToolSpec canonical format matches Anthropic's native format directly
        (``name``, ``description``, ``input_schema``), so no conversion needed.
        """
        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens

        async def _call() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "max_tokens": resolved_max_tokens,
                "system": system_prompt,
                "messages": messages,
                "tools": tools,
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            msg = await self._client.messages.create(**kwargs)  # type: ignore[arg-type]

            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []

            for block in msg.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    ))

            return LLMResponseWithTools(
                content="\n".join(text_parts) if text_parts else None,
                tool_calls=tool_calls,
                stop_reason=msg.stop_reason or "end_turn",
                model=msg.model,
                input_tokens=msg.usage.input_tokens,
                output_tokens=msg.usage.output_tokens,
                raw=msg.model_dump(),
            )

        return await llm_retry(_call, attempts=self._retry_attempts, base_delay=self._retry_base_delay)

    # ── Message-builder helpers ───────────────────────────────────────────────

    @staticmethod
    def user_message(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message_with_tools(
        text: str | None,
        tool_calls: list[ToolCall],
    ) -> dict:
        """Build the assistant turn to append after a tool-use response."""
        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": text})
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.arguments,
            })
        return {"role": "assistant", "content": content}

    @staticmethod
    def tool_result_message(tool_results: list) -> dict:
        """Build the user turn containing tool results."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": r.tool_call_id,
                "content": r.content,
                "is_error": r.is_error,
            }
            for r in tool_results
        ]
        return {"role": "user", "content": content}

