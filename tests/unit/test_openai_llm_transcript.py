from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from openforexai.adapters.llm.openai import OpenAILLMProvider


def _fake_chat_completion() -> SimpleNamespace:
    message = SimpleNamespace(content="plain response", tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=7)
    return SimpleNamespace(
        choices=[choice],
        usage=usage,
        model="gpt-5-mini",
        model_dump=lambda: {
            "choices": [
                {
                    "message": {
                        "content": "plain response",
                        "tool_calls": [],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
            "model": "gpt-5-mini",
        },
    )


def _make_async_callable(value):
    async def _call(**kwargs):
        return value

    return _call


async def test_provider_writes_full_transcript_records(tmp_path: Path) -> None:
    transcript_base_path = tmp_path / f"llm_transcript_{uuid4().hex}.log"

    # Built through the real from_config path (not __new__ + attribute stuffing)
    # so config-parsing bugs would actually surface here — only the SDK client
    # itself is swapped for a fake.
    provider = OpenAILLMProvider.from_config({
        "api_key": "test-key",
        "model": "gpt-5-mini",
        "retry_attempts": 1,
        "retry_base_delay": 0.0,
        "max_tokens": 512,
        "transcript_enabled": True,
        "transcript_path": str(transcript_base_path),
    })
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_make_async_callable(_fake_chat_completion()),
            )
        )
    )

    response = await provider.complete_with_tools(
        system_prompt="system prompt",
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
    )

    assert response.content == "plain response"
    transcript_path = provider._today_transcript_path()
    text = transcript_path.read_text(encoding="utf-8")
    assert "sender: openforexai" in text
    assert "receiver: llm_provider" in text
    assert "sender: llm_provider" in text
    assert "receiver: openforexai" in text
    assert '"messages":[{"role":"system","content":"system prompt"},{"role":"user","content":"hello"}]' in text
    assert '"content":"plain response"' in text
