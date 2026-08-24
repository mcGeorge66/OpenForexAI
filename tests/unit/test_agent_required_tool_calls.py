from __future__ import annotations

from typing import Any

import pytest

import openforexai.agents.agent as agent_module
from openforexai.agents.agent import Agent
from openforexai.messaging.bus import EventBus
from openforexai.monitoring.bus import MonitoringBus
from openforexai.ports.llm import LLMResponseWithTools, ToolCall, ToolResult
from openforexai.tools.base import ToolContext
from tests.conftest import MockRepository


def _make_agent(required_tool_calls: list[dict[str, Any]]) -> tuple[Agent, MonitoringBus]:
    monitoring_bus = MonitoringBus()
    agent = Agent(
        agent_id="OXS_T-ALL___-EA-EXAM",
        bus=EventBus(),
        repository=MockRepository(),
        monitoring_bus=monitoring_bus,
    )
    agent._system_prompt = "test system prompt"
    agent._max_tool_turns = 5
    agent._config = {"tool_config": {"required_tool_calls": required_tool_calls}}
    return agent, monitoring_bus


class _FakeDispatcher:
    """Echoes back a successful ToolResult for every ToolCall it's given."""

    _context = ToolContext(agent_id="OXS_T-ALL___-EA-EXAM")

    def visible_specs(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def execute_all(self, *, tool_calls: list[ToolCall], **_kwargs: Any) -> list[ToolResult]:
        return [
            ToolResult(tool_call_id=tc.id, name=tc.name, content="{}", is_error=False)
            for tc in tool_calls
        ]


def _text_response(text: str) -> LLMResponseWithTools:
    return LLMResponseWithTools(content=text, tool_calls=[], stop_reason="end_turn")


def _tool_call_response(name: str, arguments: dict[str, Any]) -> LLMResponseWithTools:
    return LLMResponseWithTools(
        content=None,
        tool_calls=[ToolCall(id="call_1", name=name, arguments=arguments)],
        stop_reason="tool_use",
    )


def _patch_llm_responses(monkeypatch: pytest.MonkeyPatch, responses: list[LLMResponseWithTools]) -> None:
    responses_iter = iter(responses)

    async def _fake_llm_complete_with_tools(**_kwargs: Any) -> LLMResponseWithTools:
        return next(responses_iter)

    monkeypatch.setattr(agent_module, "llm_complete_with_tools", _fake_llm_complete_with_tools)


@pytest.mark.asyncio
async def test_no_required_tool_calls_configured_behaves_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent(required_tool_calls=[])
    _patch_llm_responses(monkeypatch, [_text_response("done, nothing required")])

    final_text, _tokens, executed = await agent._run_with_tools("hello", trigger="test")

    assert final_text == "done, nothing required"
    assert executed == []
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_missing_required_tool_call_triggers_reminder_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent, monitoring_bus = _make_agent(
        required_tool_calls=[{"tool": "create_examination_report", "nudge_message": "Bitte Bericht erstellen."}]
    )
    agent._tool_dispatcher = _FakeDispatcher()  # type: ignore[assignment]

    _patch_llm_responses(
        monkeypatch,
        [
            _text_response("I am done"),  # turn 0: forgets the required tool
            _tool_call_response("create_examination_report", {"order_id": "1"}),  # turn 1: reminded, calls it
            _text_response("Now really done"),  # turn 2: final answer
        ],
    )

    final_text, _tokens, executed = await agent._run_with_tools("investigate", trigger="test")

    assert final_text == "Now really done"
    assert executed == ["create_examination_report"]
    assert monitoring_bus.pinned_events() == []


@pytest.mark.asyncio
async def test_reminders_capped_at_two_then_final_pinned_error(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent(
        required_tool_calls=[{"tool": "create_examination_report", "nudge_message": "Bitte Bericht erstellen."}]
    )

    # LLM never calls the required tool, no matter how often it's reminded.
    _patch_llm_responses(
        monkeypatch,
        [
            _text_response("done 1"),
            _text_response("done 2"),
            _text_response("done 3"),
            _text_response("done 4"),
        ],
    )

    final_text, _tokens, executed = await agent._run_with_tools("investigate", trigger="test")

    assert final_text == "done 3"  # 1 initial attempt + 2 reminders = 3 LLM turns consumed
    assert executed == []

    pinned = monitoring_bus.pinned_events()
    assert len(pinned) == 1
    assert "create_examination_report" in pinned[0]["payload"]["message"]
    assert "2 Erinnerung" in pinned[0]["payload"]["message"]


@pytest.mark.asyncio
async def test_match_arguments_requires_specific_values(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, monitoring_bus = _make_agent(
        required_tool_calls=[
            {
                "tool": "semantic_memory",
                "match_arguments": {"mode": ["remember", "update"]},
                "nudge_message": "Bitte eine Erfahrung im smem speichern.",
            }
        ]
    )
    agent._tool_dispatcher = _FakeDispatcher()  # type: ignore[assignment]

    _patch_llm_responses(
        monkeypatch,
        [
            # Calls the right tool, but with a mode that doesn't satisfy the requirement.
            _tool_call_response("semantic_memory", {"mode": "recall", "query": "x"}),
            _text_response("done"),  # still hasn't remembered/updated -> reminder should fire
            _tool_call_response("semantic_memory", {"mode": "remember", "text": "note"}),
            _text_response("done for real"),
        ],
    )

    final_text, _tokens, executed = await agent._run_with_tools("investigate", trigger="test")

    assert final_text == "done for real"
    assert executed == ["semantic_memory", "semantic_memory"]
    assert monitoring_bus.pinned_events() == []
