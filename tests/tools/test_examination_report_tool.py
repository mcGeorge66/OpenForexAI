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
    """Simulates get_order_book_entry returning a closed trade opened at 05:00 and
    closed at 08:56 (3h 56min later) — used to verify the title's start/duration label."""
    calls: list[tuple[str, dict]] = []

    async def _fake(context, operation, args):
        calls.append((operation, args))
        if operation == "get_order_book_entry":
            return {
                "opened_at": "2026-08-24T05:00:00+00:00",
                "closed_at": "2026-08-24T08:56:00+00:00",
            }
        if operation == "kb_list_documents":
            return [
                {"id": "folder-import", "title": "[Import]", "is_folder": 1, "parent_id": None},
                {"id": "folder-other", "title": "Trading Wissen", "is_folder": 1, "parent_id": None},
            ]
        return "doc-123"

    monkeypatch.setattr("openforexai.tools.system.examination_report.repo_request", _fake)
    return calls


def _kb_create_call(calls: list[tuple[str, dict]]) -> tuple[str, dict]:
    """The report's own create call — the [Import] folder may be created first."""
    return next(
        c for c in calls
        if c[0] == "kb_create_document" and not c[1]["doc"].get("is_folder")
    )


_VALID_MEMORY_WRITES = [
    {"table": "mem_agent_OXS_T-EURUSD-AA-PTJ", "id": "abc", "action": "created", "text": "first occurrence of X"},
]

_EXPECTED_TITLE = "Trade examination 2026-08-24 05:00 (3h 56min) (EURUSD)"


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
    assert result == {"document_id": "doc-123", "title": _EXPECTED_TITLE}
    _, args = _kb_create_call(fake_repo_request)
    doc = args["doc"]
    assert doc["title"] == _EXPECTED_TITLE
    assert "order-1" in doc["content"]
    assert "mem_agent_OXS_T-EURUSD-AA-PTJ" in doc["content"]
    assert "first occurrence of X" in doc["content"]
    assert "examiner-report" in doc["tags"]
    assert doc["is_folder"] is False


@pytest.mark.asyncio
async def test_title_falls_back_to_order_id_when_entry_unavailable(tool, monkeypatch):
    """If the order-book entry can't be resolved (not found, repo error, ...), the title
    must still be produced — falling back to the bare order_id like before this change."""
    async def _fake(context, operation, args):
        if operation == "get_order_book_entry":
            return None
        return "doc-123"

    monkeypatch.setattr("openforexai.tools.system.examination_report.repo_request", _fake)

    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "a",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    assert result["title"] == "Trade examination order-1 (EURUSD)"


@pytest.mark.asyncio
async def test_title_shows_start_without_duration_when_not_yet_closed(tool, monkeypatch):
    async def _fake(context, operation, args):
        if operation == "get_order_book_entry":
            return {"opened_at": "2026-08-24T05:00:00+00:00", "closed_at": None}
        return "doc-123"

    monkeypatch.setattr("openforexai.tools.system.examination_report.repo_request", _fake)

    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "a",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    assert result["title"] == "Trade examination 2026-08-24 05:00 (EURUSD)"


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
    _, args = _kb_create_call(fake_repo_request)
    assert "OXS_T-ALL___-BA-ANLYS" in args["doc"]["content"]


@pytest.mark.asyncio
async def test_report_lands_in_the_import_folder(tool, fake_repo_request):
    """Reports used to be created at the root, next to the hand-written
    documents, which buried them."""
    await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "OXS_T-EURUSD-AA-PTJ",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    _, args = _kb_create_call(fake_repo_request)
    assert args["doc"]["parent_id"] == "folder-import"
    assert not any(
        c[0] == "kb_create_document" and c[1]["doc"].get("is_folder")
        for c in fake_repo_request
    ), "der Ordner existiert bereits und darf nicht erneut angelegt werden"


@pytest.mark.asyncio
async def test_import_folder_is_created_when_missing(tool, monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def _fake(context, operation, args):
        calls.append((operation, args))
        if operation == "get_order_book_entry":
            return {"opened_at": "2026-08-24T05:00:00+00:00", "closed_at": None}
        if operation == "kb_list_documents":
            return []
        if operation == "kb_create_document" and args["doc"].get("is_folder"):
            return "fresh-folder"
        return "doc-123"

    monkeypatch.setattr("openforexai.tools.system.examination_report.repo_request", _fake)
    await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "OXS_T-EURUSD-AA-PTJ",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    folder_calls = [c for c in calls if c[0] == "kb_create_document" and c[1]["doc"].get("is_folder")]
    assert len(folder_calls) == 1
    assert folder_calls[0][1]["doc"]["title"] == "[Import]"
    _, args = _kb_create_call(calls)
    assert args["doc"]["parent_id"] == "fresh-folder"


@pytest.mark.asyncio
async def test_report_is_still_written_when_the_folder_lookup_fails(tool, monkeypatch):
    """A missing folder must never be the reason an examination has no audit
    trail — the report then lands at the root, as it did before."""
    calls: list[tuple[str, dict]] = []

    async def _fake(context, operation, args):
        calls.append((operation, args))
        if operation == "get_order_book_entry":
            return {"opened_at": "2026-08-24T05:00:00+00:00", "closed_at": None}
        if operation == "kb_list_documents":
            raise RuntimeError("repository unavailable")
        return "doc-123"

    monkeypatch.setattr("openforexai.tools.system.examination_report.repo_request", _fake)
    result = await tool.execute(
        {
            "order_id": "order-1",
            "verdict": "as_expected",
            "opening_agent_id": "OXS_T-EURUSD-AA-PTJ",
            "report_markdown": "text",
            "memory_writes": _VALID_MEMORY_WRITES,
        },
        _context(),
    )
    assert result["document_id"] == "doc-123"
    _, args = _kb_create_call(calls)
    assert args["doc"]["parent_id"] is None
