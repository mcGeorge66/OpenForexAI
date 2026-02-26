from __future__ import annotations

import json
from typing import Any

import anthropic

from openforexai.adapters.llm.base import llm_retry
from openforexai.ports.llm import AbstractLLMProvider, LLMResponse


class AnthropicLLMProvider(AbstractLLMProvider):
    """Claude adapter using the Anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-6") -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

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

        return await llm_retry(_call)

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
