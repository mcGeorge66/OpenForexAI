"""Demo unit tests for tool development.

Run:
    pytest template/tool/demo_tool_test.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from openforexai.tools.base import ToolContext
from template.tool.demo_minimal_tool import DemoMinimalTool


@pytest.mark.asyncio
async def test_demo_minimal_tool_success():
    tool = DemoMinimalTool()
    context = ToolContext(
        agent_id="TEST_ALL..._GA_TEST1",
        broker_name="TESTB",
        pair="EURUSD",
    )
    result = await tool.execute({"message": "hello"}, context)
    assert result["ok"] is True
    assert result["echo"] == "hello"
    assert result["pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_demo_minimal_tool_validates_required_argument():
    tool = DemoMinimalTool()
    context = ToolContext(agent_id="TEST_ALL..._GA_TEST1")
    with pytest.raises(ValueError):
        await tool.execute({}, context)


@pytest.mark.asyncio
async def test_context_allows_extra_values():
    tool = DemoMinimalTool()
    context = ToolContext(
        agent_id="TEST_ALL..._GA_TEST1",
        extra={"llm_name": "openai", "llm": SimpleNamespace(name="demo")},
    )
    result = await tool.execute({"message": "x"}, context)
    assert result["ok"] is True

