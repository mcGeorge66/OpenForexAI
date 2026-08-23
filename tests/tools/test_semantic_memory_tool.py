from __future__ import annotations

from typing import Any

import pytest

from openforexai.tools.base import ToolContext
from openforexai.tools.system.semantic_memory import SemanticMemoryTool


def _make_context(agent_id: str, forced_arguments: dict[str, Any] | None = None) -> ToolContext:
    agent_config = {
        "broker": "mt5_oxs_t",
        "tool_config": {
            "forced_arguments": forced_arguments if forced_arguments is not None else {},
        },
    }
    return ToolContext(
        agent_id=agent_id,
        broker_name="mt5_oxs_t",
        pair="EURUSD",
        extra={"agent_config": agent_config},
    )


@pytest.fixture
def tool() -> SemanticMemoryTool:
    return SemanticMemoryTool()


@pytest.fixture
def fake_memory_request(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake(context, operation, args):
        calls.append((operation, args))
        if operation == "remember":
            return {"id": "fake-id", "table": args["table"]}
        if operation == "update":
            return {"id": args["id"], "table": args["table"]}
        if operation == "forget":
            return {"id": args["id"], "table": args["table"], "deleted": True}
        if operation == "list_tables":
            return {"tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS", "mem_shared_mt5_oxs_t"]}
        if operation == "find_pattern":
            return {"found": True, "table": args["tables"][0], "id": "42", "text": "seen before", "pattern_key": args["pattern_key"]}
        return {"results": [{"table": args["tables"][0], "id": "1", "text": "found it", "score": 0.9}]}

    monkeypatch.setattr("openforexai.tools.system.semantic_memory.memory_request", _fake)
    return calls


@pytest.mark.asyncio
async def test_remember_with_granted_table_succeeds(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-EURUSD-AA-ANLYS",
        forced_arguments={"semantic_memory": {"write_tables": ["mem_agent_{agent_id}"], "read_tables": []}},
    )
    result = await tool.execute({"mode": "remember", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "text": "note"}, context)
    assert result == {"id": "fake-id", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS"}
    assert fake_memory_request[0][0] == "remember"
    assert fake_memory_request[0][1]["agent_id"] == "OXS_T-EURUSD-AA-ANLYS"


@pytest.mark.asyncio
async def test_remember_with_ungranted_table_denied_without_calling_backend(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-EURUSD-AA-ANLYS",
        forced_arguments={"semantic_memory": {"write_tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS"], "read_tables": []}},
    )
    result = await tool.execute({"mode": "remember", "table": "mem_shared_mt5_oxs_t", "text": "note"}, context)
    assert "error" in result
    assert fake_memory_request == []  # backend never called


@pytest.mark.asyncio
async def test_remember_with_no_forced_arguments_entry_fails_closed(tool, fake_memory_request):
    context = _make_context("OXS_T-EURUSD-AA-ANLYS", forced_arguments={})  # no semantic_memory grant at all
    result = await tool.execute({"mode": "remember", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "text": "note"}, context)
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_llm_supplied_table_grants_in_arguments_are_ignored(tool, fake_memory_request):
    """The real security property: stuffing write_tables/read_tables into the tool-call
    arguments (as an LLM might, since nothing stops arbitrary JSON keys) must have zero
    effect — grants only ever come from the agent's own server-side config."""
    context = _make_context("OXS_T-EURUSD-AA-ANLYS", forced_arguments={})
    result = await tool.execute(
        {
            "mode": "remember",
            "table": "mem_agent_OTHER-AGENT",
            "text": "note",
            "write_tables": ["mem_agent_OTHER-AGENT"],  # attempted self-grant
            "read_tables": ["mem_agent_OTHER-AGENT"],
        },
        context,
    )
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_recall_with_explicit_granted_table(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-ALL___-BA-ANLYS",
        forced_arguments={"semantic_memory": {"write_tables": [], "read_tables": ["mem_shared_{broker}"]}},
    )
    result = await tool.execute({"mode": "recall", "table": "mem_shared_mt5_oxs_t", "query": "eurusd pullback"}, context)
    assert result["results"][0]["text"] == "found it"
    assert fake_memory_request[0] == ("recall", {"tables": ["mem_shared_mt5_oxs_t"], "query": "eurusd pullback", "top_k": 5, "candidate_pool": 50})


@pytest.mark.asyncio
async def test_recall_with_omitted_table_searches_full_read_tables(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-ALL___-BA-ANLYS",
        forced_arguments={"semantic_memory": {
            "write_tables": [],
            "read_tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS", "mem_shared_{broker}"],
        }},
    )
    await tool.execute({"mode": "recall", "query": "eurusd pullback"}, context)
    assert set(fake_memory_request[0][1]["tables"]) == {"mem_agent_OXS_T-EURUSD-AA-ANLYS", "mem_shared_mt5_oxs_t"}


@pytest.mark.asyncio
async def test_recall_with_no_read_tables_denied(tool, fake_memory_request):
    context = _make_context("OXS_T-EURUSD-AA-ANLYS", forced_arguments={})
    result = await tool.execute({"mode": "recall", "query": "anything"}, context)
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_unknown_mode_returns_error(tool, fake_memory_request):
    context = _make_context("OXS_T-EURUSD-AA-ANLYS")
    result = await tool.execute({"mode": "delete_everything"}, context)
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_forget_with_granted_table_succeeds(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-EURUSD-AA-ANLYS",
        forced_arguments={"semantic_memory": {"write_tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS"], "read_tables": []}},
    )
    result = await tool.execute({"mode": "forget", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "abc"}, context)
    assert result == {"id": "abc", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "deleted": True}
    assert fake_memory_request[0] == ("forget", {"table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "abc"})


@pytest.mark.asyncio
async def test_forget_without_write_access_denied(tool, fake_memory_request):
    context = _make_context("OXS_T-EURUSD-AA-ANLYS", forced_arguments={})
    result = await tool.execute({"mode": "forget", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "abc"}, context)
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_update_with_granted_table_succeeds(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-EURUSD-AA-ANLYS",
        forced_arguments={"semantic_memory": {"write_tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS"], "read_tables": []}},
    )
    result = await tool.execute(
        {"mode": "update", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "abc", "text": "corrected"}, context,
    )
    assert result == {"id": "abc", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS"}
    assert fake_memory_request[0] == ("update", {"table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "abc", "text": "corrected"})


@pytest.mark.asyncio
async def test_update_without_write_access_denied(tool, fake_memory_request):
    context = _make_context("OXS_T-EURUSD-AA-ANLYS", forced_arguments={})
    result = await tool.execute(
        {"mode": "update", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "abc", "text": "corrected"}, context,
    )
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_wildcard_grant_allows_any_table_for_remember(tool, fake_memory_request):
    """Full-access consumers (e.g. the Chart Analysis assistant) get '*' as their grant —
    confirms an arbitrary table name is allowed, unlike a normal agent's fixed table list."""
    context = _make_context(
        "WORKBENCH-abc123",
        forced_arguments={"semantic_memory": {"write_tables": ["*"], "read_tables": ["*"]}},
    )
    result = await tool.execute({"mode": "remember", "table": "mem_shared_anything_at_all", "text": "note"}, context)
    assert result == {"id": "fake-id", "table": "mem_shared_anything_at_all"}


@pytest.mark.asyncio
async def test_wildcard_grant_recall_with_omitted_table_lists_all_tables_first(tool, fake_memory_request):
    context = _make_context(
        "WORKBENCH-abc123",
        forced_arguments={"semantic_memory": {"write_tables": ["*"], "read_tables": ["*"]}},
    )
    await tool.execute({"mode": "recall", "query": "anything"}, context)
    assert fake_memory_request[0][0] == "list_tables"
    assert fake_memory_request[1][0] == "recall"
    assert set(fake_memory_request[1][1]["tables"]) == {"mem_agent_OXS_T-EURUSD-AA-ANLYS", "mem_shared_mt5_oxs_t"}


@pytest.mark.asyncio
async def test_remember_passes_through_pattern_key(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-EURUSD-AA-ANLYS",
        forced_arguments={"semantic_memory": {"write_tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS"], "read_tables": []}},
    )
    await tool.execute(
        {"mode": "remember", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "text": "note", "pattern_key": "pat1"},
        context,
    )
    assert fake_memory_request[0][1]["pattern_key"] == "pat1"


@pytest.mark.asyncio
async def test_find_pattern_with_explicit_granted_table(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-ALL___-EA-EXAM",
        forced_arguments={"semantic_memory": {"write_tables": [], "read_tables": ["mem_shared_mt5_oxs_t"]}},
    )
    result = await tool.execute(
        {"mode": "find_pattern", "table": "mem_shared_mt5_oxs_t", "pattern_key": "pat1"}, context,
    )
    assert result["found"] is True
    assert fake_memory_request[0] == ("find_pattern", {"tables": ["mem_shared_mt5_oxs_t"], "pattern_key": "pat1"})


@pytest.mark.asyncio
async def test_find_pattern_with_omitted_table_searches_all_read_tables(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-ALL___-EA-EXAM",
        forced_arguments={"semantic_memory": {
            "write_tables": [],
            "read_tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS", "mem_shared_mt5_oxs_t"],
        }},
    )
    await tool.execute({"mode": "find_pattern", "pattern_key": "pat1"}, context)
    assert set(fake_memory_request[0][1]["tables"]) == {"mem_agent_OXS_T-EURUSD-AA-ANLYS", "mem_shared_mt5_oxs_t"}


@pytest.mark.asyncio
async def test_find_pattern_requires_pattern_key(tool, fake_memory_request):
    context = _make_context(
        "OXS_T-ALL___-EA-EXAM",
        forced_arguments={"semantic_memory": {"write_tables": [], "read_tables": ["mem_shared_mt5_oxs_t"]}},
    )
    result = await tool.execute({"mode": "find_pattern", "table": "mem_shared_mt5_oxs_t"}, context)
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_find_pattern_without_read_access_denied(tool, fake_memory_request):
    context = _make_context("OXS_T-ALL___-EA-EXAM", forced_arguments={})
    result = await tool.execute({"mode": "find_pattern", "pattern_key": "pat1"}, context)
    assert "error" in result
    assert fake_memory_request == []


@pytest.mark.asyncio
async def test_wildcard_grant_forget_allows_any_table(tool, fake_memory_request):
    context = _make_context(
        "WORKBENCH-abc123",
        forced_arguments={"semantic_memory": {"write_tables": ["*"], "read_tables": ["*"]}},
    )
    result = await tool.execute({"mode": "forget", "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS", "id": "xyz"}, context)
    assert result["deleted"] is True
