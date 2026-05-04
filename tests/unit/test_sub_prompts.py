from __future__ import annotations

from openforexai.config.config_service import ConfigService
from openforexai.tools.base import ToolContext
from openforexai.tools.system.manage_sub_prompt import ManageSubPromptTool


def test_merge_system_prompt_uses_sub_prompt_when_static_missing() -> None:
    assert ConfigService.merge_system_prompt("", "dynamic") == "dynamic"


def test_merge_system_prompt_inserts_placeholder() -> None:
    assert (
        ConfigService.merge_system_prompt("Head\n{subPrompt}\nTail", "dynamic")
        == "Head\ndynamic\nTail"
    )


def test_merge_system_prompt_appends_sub_prompt_when_no_placeholder() -> None:
    assert (
        ConfigService.merge_system_prompt("Head", "dynamic")
        == "Head\n\ndynamic"
    )


def test_merge_system_prompt_keeps_static_when_no_sub_prompt() -> None:
    assert ConfigService.merge_system_prompt("Head", None) == "Head"


async def test_manage_sub_prompt_tool_read_replace_append_delete(mock_repository) -> None:
    tool = ManageSubPromptTool()
    context = ToolContext(agent_id="TEST1-EURUSD-GA-OPT", repository=mock_repository)

    result = await tool.execute({"agent": "TARGET", "command": "read"}, context)
    assert result == {
        "agent": "TARGET",
        "command": "read",
        "prompt": None,
        "exists": False,
    }

    result = await tool.execute(
        {"agent": "TARGET", "command": "replace", "prompt": "alpha"},
        context,
    )
    assert result["prompt"] == "alpha"
    assert await mock_repository.get_sub_prompt("TARGET") == "alpha"

    result = await tool.execute(
        {"agent": "TARGET", "command": "append", "prompt": "\nbeta"},
        context,
    )
    assert result["prompt"] == "alpha\nbeta"
    assert await mock_repository.get_sub_prompt("TARGET") == "alpha\nbeta"

    result = await tool.execute({"agent": "TARGET", "command": "delete"}, context)
    assert result == {
        "agent": "TARGET",
        "command": "delete",
        "deleted": True,
    }
    assert await mock_repository.get_sub_prompt("TARGET") is None


async def test_manage_sub_prompt_tool_requires_prompt_for_replace_and_append(mock_repository) -> None:
    tool = ManageSubPromptTool()
    context = ToolContext(agent_id="TEST1-EURUSD-GA-OPT", repository=mock_repository)

    replace_result = await tool.execute({"agent": "TARGET", "command": "replace"}, context)
    append_result = await tool.execute({"agent": "TARGET", "command": "append"}, context)

    assert replace_result["error"] == "Argument 'prompt' is required for replace and append."
    assert append_result["error"] == "Argument 'prompt' is required for replace and append."
