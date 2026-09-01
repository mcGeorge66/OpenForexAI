from __future__ import annotations

from datetime import datetime
from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_duration(total_seconds: float) -> str:
    total_minutes = max(int(total_seconds // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes}min" if hours else f"{minutes}min"


async def _resolve_title_label(context: ToolContext, order_id: str) -> str:
    """'<start time> (<duration>)' for the report title, read from the authoritative
    order-book record instead of trusted from the LLM's own arguments. Falls back to
    the bare order_id if the entry can't be fetched or has no usable timestamps."""
    try:
        entry = await repo_request(context, "get_order_book_entry", {"entry_id": order_id})
    except Exception:
        entry = None
    if not isinstance(entry, dict):
        return order_id

    start = _parse_iso(entry.get("opened_at")) or _parse_iso(entry.get("requested_at"))
    if start is None:
        return order_id

    start_label = start.strftime("%Y-%m-%d %H:%M")
    end = _parse_iso(entry.get("closed_at"))
    if end is None:
        return start_label
    return f"{start_label} ({_format_duration((end - start).total_seconds())})"


class CreateExaminationReportTool(BaseTool):
    """Writes one human-readable, audit-grade report per examined trade into the
    Knowledgebase (via RepositoryService's generic kb_create_document passthrough —
    no new backend plumbing needed, it already exists for the Knowledgebase UI).

    This is the evidence trail for the Examiner agent's semantic-memory writes: every
    call requires at least one `memory_writes` entry naming the exact table/id/action/text
    that was remembered or updated, so a human (who is not required to be a trading expert)
    can see *what was concluded* and *exactly what was written to long-term memory* for
    every single closed trade — never just one or the other.
    """

    name = "create_examination_report"
    description = (
        "Create one report document in the Knowledgebase for a trade you just examined. "
        "Required for every closed trade you look at — this is the audit trail proving what "
        "you concluded and exactly what you wrote or updated in semantic_memory. Write "
        "'report_markdown' so a non-expert human can follow your reasoning. 'memory_writes' "
        "must list every semantic_memory remember/update call you made for this trade (table, "
        "the returned id, whether it was newly created or an update, and the exact text) — "
        "call semantic_memory first, then this tool with the results."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order book entry id of the trade you examined.",
            },
            "verdict": {
                "type": "string",
                "enum": [
                    "as_expected", "underperformed", "overperformed",
                    "inconclusive", "reinforced_pattern", "new_pattern",
                    "contradicts_prior_lesson",
                ],
                "description": "Your overall assessment of how this trade played out.",
            },
            "opening_agent_id": {
                "type": "string",
                "description": "The AA (or other agent) id that opened this trade.",
            },
            "execution_agent_id": {
                "type": "string",
                "description": (
                    "The BA/EventComposer id that actually executed the open and/or close — "
                    "omit if you found nothing worth noting about execution itself."
                ),
            },
            "report_markdown": {
                "type": "string",
                "description": (
                    "The report body in plain, concrete language a non-expert can follow: what "
                    "happened, what you checked, what you concluded, and why — no unexplained "
                    "jargon. Phrase any pattern/lesson as an observation, not a rule or "
                    "instruction ('in N similar cases, X tended to happen' — not 'always do X')."
                ),
            },
            "memory_writes": {
                "type": "array",
                "description": (
                    "Every semantic_memory write you made for this trade — must be non-empty. "
                    "Each entry mirrors one remember/update call you already made."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string"},
                        "id": {"type": "string"},
                        "action": {"type": "string", "enum": ["created", "updated"]},
                        "text": {"type": "string"},
                    },
                    "required": ["table", "id", "action", "text"],
                },
            },
            "pattern_key": {
                "type": "string",
                "description": "The pattern_key used for this trade's memory entry, if any.",
            },
        },
        "required": ["order_id", "verdict", "opening_agent_id", "report_markdown", "memory_writes"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        order_id = arguments.get("order_id")
        if not isinstance(order_id, str) or not order_id.strip():
            return {"error": "Argument 'order_id' is required."}

        report_markdown = arguments.get("report_markdown")
        if not isinstance(report_markdown, str) or not report_markdown.strip():
            return {"error": "Argument 'report_markdown' is required."}

        memory_writes = arguments.get("memory_writes")
        if not isinstance(memory_writes, list) or not memory_writes:
            return {
                "error": (
                    "Argument 'memory_writes' must be a non-empty list — every examined trade "
                    "must have at least one semantic_memory remember/update call to report."
                )
            }
        for entry in memory_writes:
            if not isinstance(entry, dict) or not all(
                isinstance(entry.get(k), str) and entry.get(k) for k in ("table", "id", "action", "text")
            ):
                return {"error": f"Invalid memory_writes entry (needs table/id/action/text as strings): {entry!r}"}

        verdict = arguments.get("verdict") or "inconclusive"
        opening_agent_id = arguments.get("opening_agent_id") or "unknown"
        execution_agent_id = arguments.get("execution_agent_id")
        pattern_key = arguments.get("pattern_key")

        content_parts = [
            f"# Trade-Untersuchung: {order_id}",
            "",
            f"**Pair:** {context.pair or 'unbekannt'}  ",
            f"**Untersucht von (Examiner):** {context.agent_id}  ",
            f"**Eröffnet von:** {opening_agent_id}  ",
        ]
        if execution_agent_id:
            content_parts.append(f"**Ausgeführt/geschlossen von:** {execution_agent_id}  ")
        content_parts.append(f"**Verdict:** {verdict}  ")
        if pattern_key:
            content_parts.append(f"**Pattern-Key:** `{pattern_key}`  ")
        content_parts += [
            "",
            "## Befund",
            "",
            report_markdown.strip(),
            "",
            "## Was ins Gedächtnis geschrieben oder aktualisiert wurde",
            "",
        ]
        for entry in memory_writes:
            action_label = "neu angelegt" if entry["action"] == "created" else "aktualisiert"
            content_parts.append(
                f"- Tabelle `{entry['table']}`, Eintrag `{entry['id']}` ({action_label}): {entry['text']}"
            )
        content = "\n".join(content_parts)

        tags = ["examiner-report", verdict, opening_agent_id]
        if context.pair:
            tags.append(context.pair)
        if pattern_key:
            tags.append(str(pattern_key))

        title_label = await _resolve_title_label(context, order_id)
        title = f"Trade-Untersuchung {title_label} ({context.pair or '?'})"

        doc_id = await repo_request(
            context,
            "kb_create_document",
            {
                "doc": {
                    "title": title,
                    "content": content,
                    "tags": tags,
                    "is_folder": False,
                },
            },
        )
        return {"document_id": doc_id, "title": title}
