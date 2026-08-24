from __future__ import annotations

from typing import Any

import pytest

import openforexai.agents.agent as agent_module
from openforexai.agents.agent import Agent
from openforexai.messaging.bus import EventBus
from openforexai.monitoring.bus import MonitoringBus
from openforexai.ports.llm import LLMResponseWithTools
from tests.conftest import MockRepository


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
async def test_json_not_required_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent({})
    _patch_llm_responses(monkeypatch, [_text_response("just some prose, not json")])

    final_text, _tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == "just some prose, not json"
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_valid_json_on_first_try_needs_no_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent({"require_json_response": True})
    _patch_llm_responses(monkeypatch, [_text_response('{"decision": "WAIT"}')])

    final_text, _tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == '{"decision": "WAIT"}'
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_invalid_json_triggers_nudge_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent({"require_json_response": True})
    _patch_llm_responses(
        monkeypatch,
        [
            _text_response("Sure, here is my analysis: looks bullish."),  # turn 0: not JSON
            _text_response('{"decision": "BIAS_LONG"}'),  # turn 1: corrected after nudge
        ],
    )

    final_text, _tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == '{"decision": "BIAS_LONG"}'
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_invalid_json_exhausts_reminders_then_pinned_error(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent({"require_json_response": True})
    _patch_llm_responses(
        monkeypatch,
        [
            _text_response("prose 1"),
            _text_response("prose 2"),
            _text_response("prose 3"),
            _text_response("prose 4"),
        ],
    )

    final_text, _tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == "prose 3"  # 1 initial attempt + 2 reminders

    pinned = monitoring_bus.pinned_events()
    assert len(pinned) == 1
    assert "kein gültiges JSON" in pinned[0]["payload"]["message"]
    assert "2 Erinnerung" in pinned[0]["payload"]["message"]


@pytest.mark.asyncio
async def test_configured_json_response_format_is_injected_and_reused_in_nudge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_format = '{"decision": "BIAS_LONG | BIAS_SHORT"}'
    agent, monitoring_bus = _make_agent(
        {"require_json_response": True, "json_response_format": configured_format}
    )

    captured_system_prompts: list[str] = []

    async def _fake_llm_complete_with_tools(**kwargs: Any) -> LLMResponseWithTools:
        captured_system_prompts.append(kwargs["system_prompt"])
        if len(captured_system_prompts) == 1:
            return _text_response("not json yet")
        return _text_response('{"decision": "BIAS_LONG"}')

    monkeypatch.setattr(agent_module, "llm_complete_with_tools", _fake_llm_complete_with_tools)

    final_text, _tokens, _executed = await agent._run_with_tools("hi", trigger="test")

    assert final_text == '{"decision": "BIAS_LONG"}'
    # The configured format must be injected into the system prompt on every turn,
    # not just hoped-for from hand-written prompt text.
    assert all(configured_format in p for p in captured_system_prompts)
    assert monitoring_bus.pinned_events() == []
