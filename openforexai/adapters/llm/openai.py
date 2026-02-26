from __future__ import annotations

import json
from typing import Any

import openai as _openai

from openforexai.adapters.llm.base import llm_retry
from openforexai.ports.llm import AbstractLLMProvider, LLMResponse


class OpenAILLMProvider(AbstractLLMProvider):
    """OpenAI GPT adapter (also compatible with LM Studio's OpenAI-compatible endpoint)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        self._model = model
        self._client = _openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

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
            resp = await self._client.chat.completions.create(
                model=self._model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            choice = resp.choices[0]
            return LLMResponse(
                content=choice.message.content or "",
                model=resp.model,
                input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
                output_tokens=resp.usage.completion_tokens if resp.usage else 0,
                raw=resp.model_dump(),
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


class LMStudioLLMProvider(OpenAILLMProvider):
    """LM Studio adapter (uses the OpenAI-compatible local endpoint)."""

    def __init__(self, base_url: str = "http://localhost:1234/v1", model: str = "local-model") -> None:
        super().__init__(api_key="lm-studio", model=model, base_url=base_url)
