from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from openforexai.adapters.llm.azure import AzureOpenAILLMProvider
from openforexai.agents.agent import Agent
from openforexai.models.monitoring import MonitoringEventType
from openforexai.monitoring.bus import MonitoringBus


def _fake_chat_completion() -> SimpleNamespace:
    message = SimpleNamespace(content="ok", tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=123, completion_tokens=45)
    return SimpleNamespace(
        choices=[choice],
        usage=usage,
        model="gpt-5-mini",
        model_dump=lambda: {"id": "fake"},
    )


async def test_azure_provider_emits_http_attempt_debug_callbacks() -> None:
    seen: list[tuple[str, dict]] = []
    provider = AzureOpenAILLMProvider.__new__(AzureOpenAILLMProvider)
    provider._deployment = "gpt-5-mini"
    provider._model = "gpt-5-mini"
    provider._retry_attempts = 1
    provider._retry_base_delay = 0.0
    provider._default_temperature = None
    provider._default_max_tokens = 512
    provider._debug_diagnostics_context = {}
    provider._debug_diagnostics_callback = lambda event_name, payload: seen.append((event_name, payload))
    provider._transcript_enabled = False
    provider._transcript_path = None
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_make_async_callable(_fake_chat_completion()),
            )
        )
    )

    provider.set_debug_diagnostics(lambda event_name, payload: seen.append((event_name, payload)), {"turn": 6})

    response = await provider.complete_with_tools(
        system_prompt="system",
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
    )

    assert response.content == "ok"
    assert [name for name, _ in seen] == [
        "llm_http_attempt_started",
        "llm_http_attempt_completed",
    ]
    assert seen[0][1]["turn"] == 6
    assert seen[1][1]["attempt"] == 1


def test_agent_emits_llm_debug_monitoring_events_only_in_debug_mode() -> None:
    bus = MonitoringBus(detail_level="DEBUG")

    class _Context:
        broker_name = "OXS_T"
        pair = "EURUSD"

    class _Dispatcher:
        _context = _Context()

    agent = Agent.__new__(Agent)
    agent.agent_id = "OXS_T-EURUSD-AA-ANLYS"
    agent._monitoring_bus = bus
    agent._tool_dispatcher = _Dispatcher()

    agent._emit_llm_diagnostic_event(
        MonitoringEventType.LLM_HTTP_ATTEMPT_STARTED,
        turn=6,
        attempt=1,
    )

    events = bus.recent_events(limit=10)
    assert len(events) == 1
    assert events[0].event_type == MonitoringEventType.LLM_HTTP_ATTEMPT_STARTED
    assert events[0].payload["agent_id"] == "OXS_T-EURUSD-AA-ANLYS"
    assert events[0].payload["turn"] == 6


def _make_async_callable(value):
    async def _call(**kwargs):
        return value

    return _call
