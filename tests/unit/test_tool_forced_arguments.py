from __future__ import annotations

from typing import Any

from openforexai.management.package_io import validate_package
from openforexai.ports.llm import ToolCall
from openforexai.tools.base import BaseTool, ToolContext
from openforexai.tools.dispatcher import ToolDispatcher
from openforexai.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo arguments for testing."
    input_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "level": {"type": "string", "enum": ["info", "warn"]},
        },
        "required": ["message", "level"],
    }

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.contexts: list[ToolContext] = []

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        self.calls.append(dict(arguments))
        self.contexts.append(context)
        return dict(arguments)


async def test_tool_dispatcher_overrides_llm_arguments_with_forced_values() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    dispatcher = ToolDispatcher(
        registry=registry,
        context=ToolContext(agent_id="TEST1-EURUSD-AA-TEST"),
        agent_tool_config={
            "allowed_tools": ["echo"],
            "forced_arguments": {
                "echo": {
                    "level": "warn",
                    "message": "fixed by config",
                }
            },
        },
    )

    results = await dispatcher.execute_all([
        ToolCall(
            id="call-1",
            name="echo",
            arguments={"message": "from llm", "level": "info"},
        )
    ])

    assert results[0].is_error is False
    assert tool.calls == [{"message": "fixed by config", "level": "warn"}]


async def test_tool_dispatcher_resolves_agent_placeholders_in_forced_values() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    dispatcher = ToolDispatcher(
        registry=registry,
        context=ToolContext(
            agent_id="TEST1-EURUSD-AA-ALPHA",
            broker_name="BRK01",
            pair="EURUSD",
            extra={
                "agent_config": {
                    "llm": "openai-main",
                    "broker": "paper-oanda",
                    "AnyCandle": 3,
                }
            },
        ),
        agent_tool_config={
            "allowed_tools": ["echo"],
            "forced_arguments": {
                "echo": {
                    "message": "Agent {name} on {llm}",
                    "level": "{type}",
                }
            },
        },
    )

    results = await dispatcher.execute_all([
        ToolCall(
            id="call-2",
            name="echo",
            arguments={"message": "from llm", "level": "info"},
        )
    ])

    assert results[0].is_error is False
    assert tool.calls == [{"message": "Agent ALPHA on openai-main", "level": "AA"}]


def test_visible_specs_hide_forced_arguments_from_llm_manifest() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    dispatcher = ToolDispatcher(
        registry=registry,
        context=ToolContext(agent_id="TEST1-EURUSD-AA-TEST"),
        agent_tool_config={
            "allowed_tools": ["echo"],
            "forced_arguments": {
                "echo": {"level": "warn"}
            },
        },
    )

    specs = dispatcher.visible_specs()

    assert len(specs) == 1
    schema = specs[0]["input_schema"]
    assert "level" not in schema["properties"]
    assert schema["required"] == ["message"]
    assert "Fixed by agent config: level." in specs[0]["description"]


def test_validate_package_accepts_forced_arguments_for_known_tools() -> None:
    package = {
        "agents": {
            "TEST1-EURUSD-AA-TEST": {
                "llm": "mock",
                "broker": "paper",
                "tool_config": {
                    "allowed_tools": ["echo"],
                    "forced_arguments": {
                        "echo": {"level": "warn"}
                    },
                },
            }
        }
    }

    result = validate_package(
        package,
        current_system_config={
            "modules": {
                "llm": {"mock": "config/modules/llm/mock.json5"},
                "broker": {"paper": "config/modules/broker/paper.json5"},
            }
        },
        known_tools={"echo"},
    )

    assert result["ok"] is True


def test_validate_package_rejects_unknown_forced_argument_tool() -> None:
    package = {
        "agents": {
            "TEST1-EURUSD-AA-TEST": {
                "llm": "mock",
                "broker": "paper",
                "tool_config": {
                    "allowed_tools": ["echo"],
                    "forced_arguments": {
                        "missing_tool": {"foo": "bar"}
                    },
                },
            }
        }
    }

    result = validate_package(
        package,
        current_system_config={
            "modules": {
                "llm": {"mock": "config/modules/llm/mock.json5"},
                "broker": {"paper": "config/modules/broker/paper.json5"},
            }
        },
        known_tools={"echo"},
    )

    assert result["ok"] is False
    assert any(
        problem["path"] == "agents.TEST1-EURUSD-AA-TEST.tool_config.forced_arguments.missing_tool"
        for problem in result["problems"]
    )


async def test_tool_dispatcher_allows_per_call_broker_and_pair_overrides() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    dispatcher = ToolDispatcher(
        registry=registry,
        context=ToolContext(
            agent_id="TEST1-EURUSD-AA-TEST",
            broker_name="BASE1",
            pair="EURUSD",
        ),
        agent_tool_config={"allowed_tools": ["echo"]},
    )

    results = await dispatcher.execute_all([
        ToolCall(
            id="call-3",
            name="echo",
            arguments={
                "message": "override",
                "level": "info",
                "broker": "ALTBR",
                "pair": "GBPUSD",
            },
        )
    ])

    assert results[0].is_error is False
    assert tool.calls == [{
        "message": "override",
        "level": "info",
        "broker": "ALTBR",
        "pair": "GBPUSD",
    }]
    assert len(tool.contexts) == 1
    assert tool.contexts[0].broker_name == "ALTBR"
    assert tool.contexts[0].pair == "GBPUSD"


async def test_tool_dispatcher_uses_context_when_no_per_call_override_is_given() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    base_context = ToolContext(
        agent_id="TEST1-EURUSD-AA-TEST",
        broker_name="BASE1",
        pair="EURUSD",
    )
    dispatcher = ToolDispatcher(
        registry=registry,
        context=base_context,
        agent_tool_config={"allowed_tools": ["echo"]},
    )

    results = await dispatcher.execute_all([
        ToolCall(
            id="call-4",
            name="echo",
            arguments={"message": "base", "level": "warn"},
        )
    ])

    assert results[0].is_error is False
    assert len(tool.contexts) == 1
    assert tool.contexts[0] is base_context
