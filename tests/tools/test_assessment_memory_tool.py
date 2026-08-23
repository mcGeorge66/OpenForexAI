from __future__ import annotations

from typing import Any

import pytest

from openforexai.tools.base import ToolContext
from openforexai.tools.system.assessment_memory import AssessmentMemoryTool


@pytest.fixture
def tool() -> AssessmentMemoryTool:
    return AssessmentMemoryTool()


def _context() -> ToolContext:
    return ToolContext(agent_id="chart_assistant_self")


@pytest.fixture
def fake_repo(monkeypatch):
    """In-memory stand-in for the repository, exercising the exact same
    fetch-then-concat semantics append_assessment_memory must have."""
    store: dict[str, str] = {}
    calls: list[tuple[str, dict]] = []

    async def _fake(context, operation, args):
        calls.append((operation, args))
        if operation == "get_assessment_memory":
            return store.get(args["agent"])
        if operation == "set_assessment_memory":
            store[args["agent"]] = args["message"]
            return None
        if operation == "append_assessment_memory":
            existing = store.get(args["agent"], "")
            store[args["agent"]] = f"{existing}\n{args['message']}" if existing else args["message"]
            return store[args["agent"]]
        raise AssertionError(f"unexpected operation {operation!r}")

    monkeypatch.setattr("openforexai.tools.system.assessment_memory.repo_request", _fake)
    return calls


@pytest.mark.asyncio
async def test_get_missing_note_returns_exists_false(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "get"}, _context())
    assert result == {"agentid": "a", "mode": "get", "message": None, "exists": False}


@pytest.mark.asyncio
async def test_set_then_get_round_trip(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "set", "message": "first note"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "get"}, _context())
    assert result == {"agentid": "a", "mode": "get", "message": "first note", "exists": True}


@pytest.mark.asyncio
async def test_append_to_empty_note_creates_it_without_leading_newline(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "append", "message": "first line"}, _context())
    assert result["message"] == "first line"


@pytest.mark.asyncio
async def test_append_twice_accumulates_on_new_lines(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "append", "message": "first line"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "append", "message": "second line"}, _context())
    assert result["message"] == "first line\nsecond line"


@pytest.mark.asyncio
async def test_append_does_not_require_resending_existing_content(tool, fake_repo):
    """The actual point of mode='append': the caller only ever sends the new line,
    never the growing prior content — unlike mode='set'."""
    await tool.execute({"agentid": "a", "mode": "append", "message": "line 1"}, _context())
    await tool.execute({"agentid": "a", "mode": "append", "message": "line 2"}, _context())
    append_calls = [args for op, args in fake_repo if op == "append_assessment_memory"]
    assert [c["message"] for c in append_calls] == ["line 1", "line 2"]


@pytest.mark.asyncio
async def test_set_overwrites_full_note(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "append", "message": "old content"}, _context())
    await tool.execute({"agentid": "a", "mode": "set", "message": "replacement"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "get"}, _context())
    assert result["message"] == "replacement"


@pytest.mark.asyncio
async def test_missing_agentid_rejected(tool, fake_repo):
    result = await tool.execute({"mode": "get"}, _context())
    assert "error" in result
    assert fake_repo == []


@pytest.mark.asyncio
async def test_append_without_message_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "append"}, _context())
    assert "error" in result
    assert fake_repo == []


@pytest.mark.asyncio
async def test_unknown_mode_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "delete_everything"}, _context())
    assert "error" in result
    assert fake_repo == []


# ── Section modes ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_content_on_empty_note_returns_no_sections(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "content"}, _context())
    assert result == {"agentid": "a", "mode": "content", "sections": []}


@pytest.mark.asyncio
async def test_createsection_then_content_lists_it(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "be careful on Fridays"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "content"}, _context())
    assert result["sections"] == ["risk"]


@pytest.mark.asyncio
async def test_createsection_then_readsection_round_trip(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "be careful on Fridays"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "readsection", "section": "risk"}, _context())
    assert result == {"agentid": "a", "mode": "readsection", "section": "risk", "message": "be careful on Fridays"}


@pytest.mark.asyncio
async def test_multiple_sections_stay_independent(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "note about risk"}, _context())
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "setups", "message": "note about setups"}, _context())
    content = await tool.execute({"agentid": "a", "mode": "content"}, _context())
    assert content["sections"] == ["risk", "setups"]
    risk = await tool.execute({"agentid": "a", "mode": "readsection", "section": "risk"}, _context())
    setups = await tool.execute({"agentid": "a", "mode": "readsection", "section": "setups"}, _context())
    assert risk["message"] == "note about risk"
    assert setups["message"] == "note about setups"


@pytest.mark.asyncio
async def test_createsection_duplicate_name_rejected(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "v1"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "v2"}, _context())
    assert "error" in result
    unchanged = await tool.execute({"agentid": "a", "mode": "readsection", "section": "risk"}, _context())
    assert unchanged["message"] == "v1"


@pytest.mark.asyncio
async def test_replacesection_changes_body_keeps_other_sections(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "old"}, _context())
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "setups", "message": "unrelated"}, _context())
    await tool.execute({"agentid": "a", "mode": "replacesection", "section": "risk", "message": "new"}, _context())
    risk = await tool.execute({"agentid": "a", "mode": "readsection", "section": "risk"}, _context())
    setups = await tool.execute({"agentid": "a", "mode": "readsection", "section": "setups"}, _context())
    assert risk["message"] == "new"
    assert setups["message"] == "unrelated"


@pytest.mark.asyncio
async def test_replacesection_nonexistent_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "replacesection", "section": "risk", "message": "x"}, _context())
    assert "error" in result


@pytest.mark.asyncio
async def test_readsection_nonexistent_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "readsection", "section": "risk"}, _context())
    assert "error" in result


@pytest.mark.asyncio
async def test_deletesection_removes_only_that_section(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "gone soon"}, _context())
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "setups", "message": "stays"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "deletesection", "section": "risk"}, _context())
    assert result["sections"] == ["setups"]
    content = await tool.execute({"agentid": "a", "mode": "content"}, _context())
    assert content["sections"] == ["setups"]


@pytest.mark.asyncio
async def test_deletesection_nonexistent_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "deletesection", "section": "risk"}, _context())
    assert "error" in result


@pytest.mark.asyncio
async def test_invalid_section_name_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "createsection", "section": "bad name!", "message": "x"}, _context())
    assert "error" in result


@pytest.mark.asyncio
async def test_missing_section_argument_rejected(tool, fake_repo):
    result = await tool.execute({"agentid": "a", "mode": "readsection"}, _context())
    assert "error" in result


@pytest.mark.asyncio
async def test_get_after_sections_returns_raw_text_with_markers(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "be careful"}, _context())
    result = await tool.execute({"agentid": "a", "mode": "get"}, _context())
    assert "<!-- kmem:section:risk -->" in result["message"]
    assert "be careful" in result["message"]


@pytest.mark.asyncio
async def test_preamble_before_first_section_is_preserved(tool, fake_repo):
    await tool.execute({"agentid": "a", "mode": "set", "message": "some unstructured scratch note"}, _context())
    await tool.execute({"agentid": "a", "mode": "createsection", "section": "risk", "message": "structured"}, _context())
    raw = await tool.execute({"agentid": "a", "mode": "get"}, _context())
    assert "some unstructured scratch note" in raw["message"]
    section = await tool.execute({"agentid": "a", "mode": "readsection", "section": "risk"}, _context())
    assert section["message"] == "structured"
