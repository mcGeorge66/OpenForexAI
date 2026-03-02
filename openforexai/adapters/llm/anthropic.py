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
    ) -> None:
        self._model = model
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @classmethod
    def from_config(cls, cfg: dict) -> "AnthropicLLMProvider":
        return cls(
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "claude-opus-4-6"),
            retry_attempts=cfg.get("retry_attempts", 3),
            retry_base_delay=cfg.get("retry_base_delay", 1.0),
        )

    @property
    def model_id(self) -> str:
        return self._model

    # ── Simple completions ────────────────────────────────────────────────────

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        async def _call() -> LLMResponse:
            msg = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
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
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponseWithTools:
        """Single turn using Anthropic's native tool_use API.

        ToolSpec canonical format matches Anthropic's native format directly
        (``name``, ``description``, ``input_schema``), so no conversion needed.
        """
        async def _call() -> LLMResponseWithTools:
            msg = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
                tools=tools,  # type: ignore[arg-type]
            )

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
