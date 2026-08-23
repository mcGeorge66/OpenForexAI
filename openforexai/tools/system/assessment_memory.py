from __future__ import annotations

import re
from typing import Any

from openforexai.tools.base import BaseTool, ToolContext, repo_request

# A section boundary is a fixed, unambiguous technical marker on its own line — never a
# Markdown heading — so it can never collide with ordinary text/markdown the agent (or a
# human editing via mode='set') might write for unrelated reasons. Everything from one
# marker up to the next marker (or end of text) is that section's body.
_SECTION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SECTION_MARKER_RE = re.compile(r"^<!-- kmem:section:([A-Za-z0-9_-]{1,64}) -->$")


def _marker(name: str) -> str:
    return f"<!-- kmem:section:{name} -->"


def _parse_sections(raw: str) -> tuple[str, list[tuple[str, str]]]:
    """Split raw note text into (preamble, [(section_name, body), ...]) in document order.
    'preamble' is any content before the first section marker (usually empty once the note
    is organized into sections, but preserved rather than discarded if present)."""
    lines = raw.split("\n") if raw else []
    preamble_lines: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_body: list[str] = []

    for line in lines:
        match = _SECTION_MARKER_RE.match(line.strip())
        if match:
            if current_name is not None:
                sections.append((current_name, current_body))
            current_name = match.group(1)
            current_body = []
        elif current_name is None:
            preamble_lines.append(line)
        else:
            current_body.append(line)
    if current_name is not None:
        sections.append((current_name, current_body))

    return "\n".join(preamble_lines), [(name, "\n".join(body)) for name, body in sections]


def _render(preamble: str, sections: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if preamble.strip():
        parts.append(preamble.strip("\n"))
    for name, body in sections:
        parts.append(_marker(name))
        if body:
            parts.append(body)
    return "\n".join(parts)


class AssessmentMemoryTool(BaseTool):
    name = "assessment_memory"
    description = (
        "Your persisted, free-text note for a target agent id — one note per id, e.g. useful "
        "as your own personal scratchpad across conversations. A note can optionally be "
        "organized into named sections (stable handles that survive edits, unlike line "
        "numbers) — build up structure with createsection instead of one giant blob.\n"
        "mode='get' reads the whole raw note (all sections included). mode='set' overwrites "
        "the whole note — only for a deliberate full rewrite/reset. mode='append' adds "
        "'message' as a new line onto the end of the whole note without resending existing "
        "content (lands after the last section if any exist).\n"
        "Section modes: mode='content' lists the existing section names (your table of "
        "contents) — check this before creating a new section to see what's already there. "
        "mode='readsection' (needs 'section') reads just that section's body. "
        "mode='createsection' (needs 'section', 'message') adds a brand-new section at the "
        "end — fails if that name already exists, use replacesection to change an existing "
        "one instead. mode='replacesection' (needs 'section', 'message') replaces an existing "
        "section's whole body — fails if it doesn't exist yet, use createsection first. "
        "mode='deletesection' (needs 'section') removes a section entirely."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agentid": {"type": "string", "description": "Target agent id (or your own fixed scratchpad id)."},
            "mode": {
                "type": "string",
                "enum": [
                    "get", "set", "append",
                    "content", "readsection", "replacesection", "createsection", "deletesection",
                ],
                "description": "Operation to perform.",
            },
            "message": {
                "type": "string",
                "description": (
                    "Full text for mode='set'; line to add for mode='append'; section body for "
                    "mode='createsection'/'replacesection'."
                ),
            },
            "section": {
                "type": "string",
                "description": (
                    "Section name (letters/digits/underscore/hyphen only) — required for "
                    "readsection/replacesection/createsection/deletesection."
                ),
            },
        },
        "required": ["agentid", "mode"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        agentid = str(arguments.get("agentid", "")).strip()
        mode = str(arguments.get("mode", "")).strip().lower()

        if not agentid:
            return {"error": "Argument 'agentid' is required."}

        if mode == "get":
            message = await repo_request(context, "get_assessment_memory", {"agent": agentid})
            return {"agentid": agentid, "mode": mode, "message": message, "exists": message is not None}

        if mode == "set":
            message = arguments.get("message")
            if not isinstance(message, str):
                return {"error": "Argument 'message' is required for mode='set'."}
            await repo_request(context, "set_assessment_memory", {"agent": agentid, "message": message})
            return {"agentid": agentid, "mode": mode, "message": message, "length": len(message)}

        if mode == "append":
            message = arguments.get("message")
            if not isinstance(message, str) or not message.strip():
                return {"error": "Argument 'message' is required for mode='append'."}
            full_message = await repo_request(context, "append_assessment_memory", {"agent": agentid, "message": message})
            return {"agentid": agentid, "mode": mode, "message": full_message, "length": len(full_message)}

        if mode in ("content", "readsection", "replacesection", "createsection", "deletesection"):
            return await self._section_op(mode, agentid, arguments, context)

        return {"error": f"Unsupported mode: {mode!r}."}

    async def _section_op(
        self, mode: str, agentid: str, arguments: dict[str, Any], context: ToolContext
    ) -> Any:
        raw = await repo_request(context, "get_assessment_memory", {"agent": agentid}) or ""
        preamble, sections = _parse_sections(raw)
        names = [name for name, _ in sections]

        if mode == "content":
            return {"agentid": agentid, "mode": mode, "sections": names}

        section = arguments.get("section")
        if not isinstance(section, str) or not _SECTION_NAME_RE.match(section):
            return {
                "error": (
                    "Argument 'section' is required and must match "
                    "[A-Za-z0-9_-]{1,64} for this mode."
                )
            }

        index = next((i for i, name in enumerate(names) if name == section), None)

        if mode == "readsection":
            if index is None:
                return {"error": f"Section {section!r} does not exist. Existing sections: {names}"}
            return {"agentid": agentid, "mode": mode, "section": section, "message": sections[index][1]}

        if mode == "createsection":
            if index is not None:
                return {"error": f"Section {section!r} already exists — use mode='replacesection' to change it."}
            message = arguments.get("message")
            if not isinstance(message, str):
                return {"error": "Argument 'message' is required for mode='createsection'."}
            sections.append((section, message))
            await repo_request(context, "set_assessment_memory", {"agent": agentid, "message": _render(preamble, sections)})
            return {"agentid": agentid, "mode": mode, "section": section, "sections": [n for n, _ in sections]}

        if mode == "replacesection":
            if index is None:
                return {"error": f"Section {section!r} does not exist. Existing sections: {names}. Use mode='createsection' to add it."}
            message = arguments.get("message")
            if not isinstance(message, str):
                return {"error": "Argument 'message' is required for mode='replacesection'."}
            sections[index] = (section, message)
            await repo_request(context, "set_assessment_memory", {"agent": agentid, "message": _render(preamble, sections)})
            return {"agentid": agentid, "mode": mode, "section": section}

        if mode == "deletesection":
            if index is None:
                return {"error": f"Section {section!r} does not exist. Existing sections: {names}"}
            del sections[index]
            await repo_request(context, "set_assessment_memory", {"agent": agentid, "message": _render(preamble, sections)})
            return {"agentid": agentid, "mode": mode, "section": section, "sections": [n for n, _ in sections]}

        return {"error": f"Unsupported mode: {mode!r}."}
