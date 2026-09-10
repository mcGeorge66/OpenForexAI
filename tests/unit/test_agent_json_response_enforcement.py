from __future__ import annotations

import json
from typing import Any

import pytest

import openforexai.agents.agent as agent_module
from openforexai.agents.agent import Agent
from openforexai.messaging.bus import EventBus
from openforexai.monitoring.bus import MonitoringBus
from openforexai.ports.llm import LLMResponseWithTools, LLMStructuredResponse
from tests.conftest import MockRepository

_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string"}},
}


def _make_agent(tool_config: dict[str, Any]) -> tuple[Agent, MonitoringBus]:
    monitoring_bus = MonitoringBus()
    agent = Agent(
        agent_id="OXS_T-EURUSD-AA-PTJ",
        bus=EventBus(),
        repository=MockRepository(),
        monitoring_bus=monitoring_bus,
    )
    agent._system_prompt = "base system prompt"
    agent._max_tool_turns = 5
    agent._config = {"tool_config": tool_config}
    return agent, monitoring_bus


def _text_response(text: str | None) -> LLMResponseWithTools:
    return LLMResponseWithTools(content=text, tool_calls=[], stop_reason="end_turn")


def _patch_llm_responses(monkeypatch: pytest.MonkeyPatch, responses: list[LLMResponseWithTools]) -> None:
    responses_iter = iter(responses)

    async def _fake_llm_complete_with_tools(**_kwargs: Any) -> LLMResponseWithTools:
        return next(responses_iter)

    monkeypatch.setattr(agent_module, "llm_complete_with_tools", _fake_llm_complete_with_tools)


@pytest.mark.asyncio
async def test_no_schema_configured_returns_raw_content_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agents without response_schema (chat assistants, EA reports, ...) are byte-for-byte
    unaffected — this is the regression guard for every agent that isn't opting in."""
    agent, monitoring_bus = _make_agent({})
    _patch_llm_responses(monkeypatch, [_text_response("just some prose, not json")])

    final_text, _tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == "just some prose, not json"
    assert agent._last_schema_enforced is False
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_response_schema_forces_structured_finalize_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """With response_schema configured, the free-form turn's content is discarded and the
    real final answer comes from the schema-enforced complete_structured call instead."""
    agent, monitoring_bus = _make_agent(
        {"response_schema": _SCHEMA, "response_schema_name": "agent_result"}
    )
    _patch_llm_responses(monkeypatch, [_text_response("some free-form prose the model wrote")])

    captured_kwargs: dict[str, Any] = {}

    async def _fake_llm_complete_structured(**kwargs: Any) -> LLMStructuredResponse:
        captured_kwargs.update(kwargs)
        return LLMStructuredResponse(
            parsed={"decision": "WAIT"}, model="mock", input_tokens=10, output_tokens=5, raw={},
        )

    monkeypatch.setattr(agent_module, "llm_complete_structured", _fake_llm_complete_structured)

    final_text, total_tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == json.dumps({"decision": "WAIT"})
    assert agent._last_schema_enforced is True
    assert total_tokens == 15
    assert captured_kwargs["response_schema"] == _SCHEMA
    assert captured_kwargs["schema_name"] == "agent_result"
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_response_schema_name_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, _monitoring_bus = _make_agent({"response_schema": _SCHEMA})
    _patch_llm_responses(monkeypatch, [_text_response("prose")])

    captured_kwargs: dict[str, Any] = {}

    async def _fake_llm_complete_structured(**kwargs: Any) -> LLMStructuredResponse:
        captured_kwargs.update(kwargs)
        return LLMStructuredResponse(parsed={}, model="mock", input_tokens=0, output_tokens=0, raw={})

    monkeypatch.setattr(agent_module, "llm_complete_structured", _fake_llm_complete_structured)

    await agent._run_with_tools("hi", trigger="test")

    assert captured_kwargs["schema_name"] == "agent_result"
