from __future__ import annotations

from types import SimpleNamespace

import pytest

from openforexai.adapters.llm.anthropic import AnthropicLLMProvider
from openforexai.adapters.llm.openai import OpenAILLMProvider

_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["WAIT", "GO"]},
        "nested": {
            "type": "object",
            "properties": {"value": {"type": ["number", "null"]}},
        },
    },
}


def _make_async_callable(value):
    async def _call(**kwargs):
        _call.last_kwargs = kwargs
        return value

    _call.last_kwargs = None
    return _call


# ── OpenAI ──────────────────────────────────────────────────────────────────

def _fake_openai_completion(content: str | None) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=7)
    return SimpleNamespace(
        choices=[choice], usage=usage, model="gpt-5.6-luna",
        model_dump=lambda: {"choices": [], "usage": {}, "model": "gpt-5.6-luna"},
    )


@pytest.mark.asyncio
async def test_openai_complete_structured_sends_strict_json_schema() -> None:
    provider = OpenAILLMProvider.from_config({
        "api_key": "test-key", "model": "gpt-5.6-luna",
        "retry_attempts": 1, "retry_base_delay": 0.0, "max_tokens": 512,
    })
    fake_create = _make_async_callable(_fake_openai_completion('{"decision": "WAIT", "nested": {"value": null}}'))
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))

    result = await provider.complete_structured(
        system_prompt="system",
        messages=[{"role": "user", "content": "hi"}],
        response_schema=_SCHEMA,
        schema_name="agent_result",
    )

    assert result.parsed == {"decision": "WAIT", "nested": {"value": None}}
    sent = fake_create.last_kwargs
    assert sent["response_format"]["type"] == "json_schema"
    json_schema = sent["response_format"]["json_schema"]
    assert json_schema["name"] == "agent_result"
    assert json_schema["strict"] is True
    # Strict-mode requirements are auto-derived, not hand-authored — every level.
    assert json_schema["schema"]["required"] == ["decision", "nested"]
    assert json_schema["schema"]["additionalProperties"] is False
    assert json_schema["schema"]["properties"]["nested"]["required"] == ["value"]
    assert json_schema["schema"]["properties"]["nested"]["additionalProperties"] is False
    # No tools passed in -> no tools/tool_choice on the request at all.
    assert "tools" not in sent
    assert "tool_choice" not in sent


@pytest.mark.asyncio
async def test_openai_complete_structured_raises_on_empty_content() -> None:
    provider = OpenAILLMProvider.from_config({
        "api_key": "test-key", "model": "gpt-5.6-luna",
        "retry_attempts": 1, "retry_base_delay": 0.0, "max_tokens": 512,
    })
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_make_async_callable(_fake_openai_completion(None))))
    )

    with pytest.raises(RuntimeError, match="no content"):
        await provider.complete_structured(
            system_prompt="system", messages=[{"role": "user", "content": "hi"}],
            response_schema=_SCHEMA, schema_name="agent_result",
        )


# ── Anthropic ─────────────────────────────────────────────────────────────

def _fake_anthropic_message(schema_name: str, tool_input: dict) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", name=schema_name, input=tool_input)
    usage = SimpleNamespace(input_tokens=20, output_tokens=8)
    return SimpleNamespace(
        content=[block], stop_reason="tool_use", model="claude-opus-4-6", usage=usage,
        model_dump=lambda: {"content": [], "model": "claude-opus-4-6"},
    )


@pytest.mark.asyncio
async def test_anthropic_complete_structured_forces_tool_choice() -> None:
    provider = AnthropicLLMProvider.from_config({
        "api_key": "test-key", "model": "claude-opus-4-6",
        "retry_attempts": 1, "retry_base_delay": 0.0, "max_tokens": 512,
    })
    fake_create = _make_async_callable(_fake_anthropic_message("agent_result", {"decision": "WAIT"}))
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))

    result = await provider.complete_structured(
        system_prompt="system", messages=[{"role": "user", "content": "hi"}],
        response_schema=_SCHEMA, schema_name="agent_result",
    )

    assert result.parsed == {"decision": "WAIT"}
    sent = fake_create.last_kwargs
    assert sent["tool_choice"] == {"type": "tool", "name": "agent_result"}
    tool_names = [t["name"] for t in sent["tools"]]
    assert tool_names == ["agent_result"]
    assert sent["tools"][0]["input_schema"] == _SCHEMA


@pytest.mark.asyncio
async def test_anthropic_complete_structured_raises_if_schema_tool_missing() -> None:
    provider = AnthropicLLMProvider.from_config({
        "api_key": "test-key", "model": "claude-opus-4-6",
        "retry_attempts": 1, "retry_base_delay": 0.0, "max_tokens": 512,
    })
    empty_message = SimpleNamespace(
        content=[], stop_reason="end_turn", model="claude-opus-4-6",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        model_dump=lambda: {},
    )
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=_make_async_callable(empty_message)))

    with pytest.raises(RuntimeError, match="agent_result"):
        await provider.complete_structured(
            system_prompt="system", messages=[{"role": "user", "content": "hi"}],
            response_schema=_SCHEMA, schema_name="agent_result",
        )
