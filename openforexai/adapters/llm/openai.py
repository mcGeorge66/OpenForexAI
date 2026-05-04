from __future__ import annotations

import json
from typing import Any

import openai as _openai

from openforexai.adapters.llm.base import llm_retry
from openforexai.ports.llm import (
    AbstractLLMProvider,
    LLMResponse,
    LLMResponseWithTools,
    ToolCall,
    ToolSpec,
)


def _to_openai_tool(spec: ToolSpec) -> dict:
    """Convert canonical ToolSpec (Anthropic-style) to OpenAI function format."""
    return {
        "type": "function",
        "function": {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "parameters": spec.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


class OpenAILLMProvider(AbstractLLMProvider):
    """OpenAI GPT adapter."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        default_temperature: float | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self._client = _openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    @classmethod
    def from_config(cls, cfg: dict) -> OpenAILLMProvider:
        return cls(
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "gpt-4o"),
            base_url=cfg.get("base_url") or None,
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
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_tokens"] = resolved_max_tokens
            resp = await self._client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            return LLMResponse(
                content=choice.message.content or "",
                model=resp.model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                raw=resp.model_dump(),
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
        """Single turn using OpenAI's native function-calling API."""
        openai_tools = [_to_openai_tool(t) for t in tools]

        # Prepend system message
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens

        async def _call() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": full_messages,
                "tools": openai_tools,
                "tool_choice": "auto",
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_tokens"] = resolved_max_tokens
            resp = await self._client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            msg = choice.message

            tool_calls: list[ToolCall] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    ))

            stop_reason = choice.finish_reason or "end_turn"
            if stop_reason == "tool_calls":
                stop_reason = "tool_use"

            return LLMResponseWithTools(
                content=msg.content or None,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                model=resp.model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                raw=resp.model_dump(),
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
        openai_tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in tool_calls
        ]
        return {
            "role": "assistant",
            "content": text,
            "tool_calls": openai_tool_calls,
        }

    @staticmethod
    def tool_result_message(tool_results: list) -> list[dict]:
        """Build tool-result turns (OpenAI uses one message per result)."""
        return [
            {
                "role": "tool",
                "tool_call_id": r.tool_call_id,
                "content": r.content,
            }
            for r in tool_results
        ]

