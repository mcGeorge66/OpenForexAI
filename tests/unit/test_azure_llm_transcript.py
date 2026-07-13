from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from openforexai.adapters.llm.azure import AzureOpenAILLMProvider


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


async def test_azure_provider_writes_full_transcript_records() -> None:
    transcript_path = Path.cwd() / ".tmp" / f"azure_llm_transcript_{uuid4().hex}.log"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    if transcript_path.exists():
        transcript_path.unlink()

    provider = AzureOpenAILLMProvider.__new__(AzureOpenAILLMProvider)
    provider._deployment = "gpt-5-mini"
    provider._model = "gpt-5-mini"
    provider._retry_attempts = 1
    provider._retry_base_delay = 0.0
    provider._default_temperature = None
    provider._default_max_tokens = 512
    provider._debug_diagnostics_context = {"agent_id": "OXS_T-EURUSD-AA-ANLYS", "turn": 6}
    provider._debug_diagnostics_callback = None
    provider._transcript_enabled = True
    provider._transcript_path = transcript_path
    import asyncio
    provider._transcript_lock = asyncio.Lock()
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
    text = transcript_path.read_text(encoding="utf-8")
    assert "sender: openforexai" in text
    assert "receiver: azure_openai" in text
    assert "sender: azure_openai" in text
    assert "receiver: openforexai" in text
    assert '"messages":[{"role":"system","content":"system prompt"},{"role":"user","content":"hello"}]' in text
    assert '"content":"plain response"' in text
    transcript_path.unlink(missing_ok=True)
