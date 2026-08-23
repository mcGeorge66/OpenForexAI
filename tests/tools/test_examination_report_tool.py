from __future__ import annotations

from typing import Any

import pytest

from openforexai.tools.base import ToolContext
from openforexai.tools.system.examination_report import CreateExaminationReportTool


@pytest.fixture
def tool() -> CreateExaminationReportTool:
    return CreateExaminationReportTool()


def _context() -> ToolContext:
    return ToolContext(agent_id="OXS_T-ALL___-EA-EXAM", broker_name="mt5_oxs_t", pair="EURUSD")


@pytest.fixture
def fake_repo_request(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake(context, operation, args):
        calls.append((operation, args))
        return "doc-123"

    monkeypatch.setattr("openforexai.tools.system.examination_report.repo_request", _fake)
    return calls


_VALID_MEMORY_WRITES = [
    {"table": "mem_agent_OXS_T-EURUSD-AA-PTJ", "id": "abc", "action": "created", "text": "first occurrence of X"},
]


@pytest.mark.asyncio
async def test_creates_kb_document_with_expected_fields(tool, fake_repo_request):
    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "OXS_T-EURUSD-AA-PTJ",
            "report_markdown": "The trade played out as the opening analysis expected.",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    assert result == {"document_id": "doc-123", "title": "Trade-Untersuchung order-1 (EURUSD)"}
    assert fake_repo_request[0][0] == "kb_create_document"
    doc = fake_repo_request[0][1]["doc"]
    assert doc["title"] == "Trade-Untersuchung order-1 (EURUSD)"
    assert "order-1" in doc["content"]
    assert "mem_agent_OXS_T-EURUSD-AA-PTJ" in doc["content"]
    assert "first occurrence of X" in doc["content"]
    assert "examiner-report" in doc["tags"]
    assert doc["is_folder"] is False


@pytest.mark.asyncio
async def test_missing_order_id_rejected(tool, fake_repo_request):
    result = await tool.execute(
        {
            "verdict": "as_expected",
            "opening_agent_id": "a",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    assert "error" in result
    assert fake_repo_request == []


@pytest.mark.asyncio
async def test_empty_memory_writes_rejected(tool, fake_repo_request):
    """The core evidentiary requirement: every examined trade must report at least
    one semantic_memory write — an empty list must never silently pass."""
    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "a",
            "report_markdown": "text",
            "memory_writes": [],
        },
        _context(),
    )
    assert "error" in result
    assert fake_repo_request == []


@pytest.mark.asyncio
async def test_malformed_memory_writes_entry_rejected(tool, fake_repo_request):
    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "a",
            "report_markdown": "text",
            "memory_writes": [{"table": "mem_agent_x", "id": "abc"}],  # missing action/text
        },
        _context(),
    )
    assert "error" in result
    assert fake_repo_request == []


@pytest.mark.asyncio
async def test_missing_report_markdown_rejected(tool, fake_repo_request):
    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "a",
            "report_markdown": "   ",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    assert "error" in result
    assert fake_repo_request == []


@pytest.mark.asyncio
async def test_execution_agent_id_included_when_given(tool, fake_repo_request):
    await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "underperformed",
            "opening_agent_id": "OXS_T-EURUSD-AA-PTJ",
            "execution_agent_id": "OXS_T-ALL___-BA-ANLYS",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    doc = fake_repo_request[0][1]["doc"]
    assert "OXS_T-ALL___-BA-ANLYS" in doc["content"]
