from __future__ import annotations

import json
from typing import Any

from openai import AsyncAzureOpenAI

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


class AzureOpenAILLMProvider(AbstractLLMProvider):
    """Azure OpenAI adapter using the OpenAI SDK's AzureOpenAI client."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-12-01-preview",
        model: str | None = None,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        default_temperature: float | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        # Azure routes requests by deployment name; model_id is used for logging only
        self._deployment = deployment
        self._model = model or deployment
        self._retry_attempts = retry_attempts
        self._retry_base_delay = retry_base_delay
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    @classmethod
    def from_config(cls, cfg: dict) -> "AzureOpenAILLMProvider":
        return cls(
            api_key=cfg.get("api_key", ""),
            endpoint=cfg.get("endpoint", ""),
            deployment=cfg.get("deployment", ""),
            api_version=cfg.get("api_version", "2024-12-01-preview"),
            model=cfg.get("model") or cfg.get("deployment", ""),
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
                "model": self._deployment,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = resolved_max_tokens
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
        """Single turn using Azure OpenAI's native function-calling API."""
        openai_tools = [_to_openai_tool(t) for t in tools]
        full_messages = [{"role": "system", "content": system_prompt}] + [
            self._sanitize_message(m) for m in messages
        ]

        resolved_temp = self._default_temperature if temperature is None else temperature
        resolved_max_tokens = self._default_max_tokens if max_tokens is None else max_tokens

        async def _call_with_tools() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._deployment,
                "messages": full_messages,
                "tools": openai_tools,
                "tool_choice": "auto",
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = resolved_max_tokens
            resp = await self._client.chat.completions.create(**kwargs)
            return self._parse_chat_completion(resp)

        async def _call_without_tools() -> LLMResponseWithTools:
            kwargs: dict[str, Any] = {
                "model": self._deployment,
                "messages": full_messages,
            }
            if resolved_temp is not None:
                kwargs["temperature"] = resolved_temp
            if resolved_max_tokens is not None:
                kwargs["max_completion_tokens"] = min(resolved_max_tokens, 1024)
            resp = await self._client.chat.completions.create(**kwargs)
            parsed = self._parse_chat_completion(resp)
            # No tools were offered in fallback mode.
            return LLMResponseWithTools(
                content=parsed.content,
                tool_calls=[],
                stop_reason="end_turn",
                model=parsed.model,
                input_tokens=parsed.input_tokens,
                output_tokens=parsed.output_tokens,
                raw=parsed.raw,
            )

        try:
            return await llm_retry(
                _call_with_tools,
                attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
            )
        except RuntimeError as exc:
            # Some Azure deployments intermittently reject valid tool prompts with
            # 400 invalid_prompt/internal error. Degrade to text-only response so
            # the agent loop continues instead of crashing.
            if openai_tools and "invalid_prompt" in str(exc).lower():
                return await llm_retry(
                    _call_without_tools,
                    attempts=1,
                    base_delay=self._retry_base_delay,
                )
            raise

    # ── Message-builder helpers ───────────────────────────────────────────────

    @staticmethod
    def user_message(content: str) -> dict:
        return {"role": "user", "content": content}

    @staticmethod
    def assistant_message_with_tools(
        text: str | None,
        tool_calls: list[ToolCall],
    ) -> dict:
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
            # Azure chat/completions can reject assistant turns with null content.
            # Keep a string payload for compatibility across API versions.
            "content": text or "",
            "tool_calls": openai_tool_calls,
        }

    @staticmethod
    def tool_result_message(tool_results: list) -> list[dict]:
        return [
            {
                "role": "tool",
                "tool_call_id": r.tool_call_id,
                "content": r.content if isinstance(r.content, str) else json.dumps(r.content, default=str),
            }
            for r in tool_results
        ]

    @staticmethod
    def _sanitize_message(message: dict[str, Any]) -> dict[str, Any]:
        """Normalize message content to Azure-compatible payload shapes."""
        m = dict(message)
        if "content" not in m:
            return m
        content = m.get("content")
        if content is None:
            m["content"] = ""
        elif not isinstance(content, (str, list)):
            m["content"] = json.dumps(content, default=str)
        return m

    @staticmethod
    def _parse_chat_completion(resp: Any) -> LLMResponseWithTools:
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

