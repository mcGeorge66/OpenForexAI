"""Demo tests for LLM provider templates."""
from __future__ import annotations

import pytest

from template.llm.demo_llm_provider import DemoLLMProvider


@pytest.mark.asyncio
async def test_demo_complete():
    p = DemoLLMProvider(model="demo")
    r = await p.complete("sys", "hello")
    assert "hello" in r.content


@pytest.mark.asyncio
async def test_demo_complete_with_tools():
    p = DemoLLMProvider(model="demo")
    resp = await p.complete_with_tools(
        "sys",
        messages=[{"role": "user", "content": "please call_tool"}],
        tools=[{"name": "demo_tool", "description": "", "input_schema": {"type": "object"}}],
    )
    assert resp.stop_reason == "tool_use"
    assert len(resp.tool_calls) == 1

