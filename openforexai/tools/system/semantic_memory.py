from __future__ import annotations

from typing import Any

from openforexai.tools.argument_templates import (
    build_agent_placeholder_values,
    resolve_argument_templates,
)
from openforexai.tools.base import BaseTool, ToolContext, memory_request


class SemanticMemoryTool(BaseTool):
    name = "semantic_memory"
    description = (
        "Store, search, modify, or delete long-term semantic memories. mode='remember' saves a "
        "note of text to a memory table; mode='recall' searches memory table(s) for entries "
        "relevant to a query, ranked by similarity; mode='update' changes an existing memory's "
        "text/tags/importance (needs 'id'); mode='forget' deletes a memory by id; "
        "mode='find_pattern' looks up an EXACT match by 'pattern_key' (not fuzzy — use this to "
        "reliably answer 'have we seen this exact setup before?' instead of trusting a "
        "similarity score). Which tables you may write to or read from is restricted per-agent "
        "by the system — just call with the mode and (optionally) the table you need; if you "
        "lack access to a table, the tool returns a clear error explaining that instead of "
        "failing silently. For recall and find_pattern, omitting 'table' searches across every "
        "table you are allowed to read."
    )

    # NOTE: write_tables/read_tables ARE declared below (so the Agent Config Wizard's
    # forced_arguments validator recognizes them, and so the dispatcher hides them from
    # the LLM when an agent's forced_arguments sets them — same mechanism auto_place_order
    # uses for order_type). Critically, execute()/_resolve_grants() below NEVER read these
    # two keys from `arguments` — access is resolved exclusively from the agent's own live
    # config (context.extra["agent_config"]). So even for an agent with no forced_arguments
    # entry at all (where the dispatcher would leave these visible/LLM-fillable), whatever
    # value the LLM supplies for them is simply never consulted — there is no code path by
    # which a tool-call argument can influence which tables this agent may touch.
    input_schema = {
        "type": "object",
        "properties": {
            "write_tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Server-controlled — set via this agent's forced_arguments config, "
                    "never by the caller. Any value supplied here is ignored."
                ),
            },
            "read_tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Server-controlled — set via this agent's forced_arguments config, "
                    "never by the caller. Any value supplied here is ignored."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["remember", "recall", "update", "forget", "find_pattern"],
                "description": (
                    "'remember' stores a memory, 'recall' searches, 'update' edits an existing "
                    "memory's text/tags/importance (needs 'id'), 'forget' deletes one (needs 'id'), "
                    "'find_pattern' does an exact lookup by 'pattern_key'."
                ),
            },
            "table": {
                "type": "string",
                "description": (
                    "Table to act on. Required for remember/update/forget. Optional for recall — "
                    "if omitted, all tables you can read are searched."
                ),
            },
            "id": {
                "type": "string",
                "description": "The memory's id (as returned by a prior remember/recall). Required for mode='update' and mode='forget'.",
            },
            "text": {
                "type": "string",
                "description": "The content to store. Required for mode='remember'. For mode='update', omit to leave the text unchanged.",
            },
            "query": {
                "type": "string",
                "description": "What to search for. Required for mode='recall'.",
            },
            "top_k": {
                "type": "integer",
                "description": "Max number of results to return for mode='recall'. Default 5.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags to attach to the memory (mode='remember'), or to replace them with (mode='update').",
            },
            "importance": {
                "type": "number",
                "description": "Importance of the memory, 0-1. Default 0.5 (mode='remember'). Also settable on mode='update'.",
            },
            "expiry_days": {
                "type": "integer",
                "description": "Optional: number of days until this memory expires (mode='remember'). Omit for no expiry.",
            },
            "pattern_key": {
                "type": "string",
                "description": (
                    "A stable, short, exact-match key you assign to identify a recurring setup/pattern "
                    "type (e.g. 'eurusd_h1_uptrend_resistance_rebound'). Set it on mode='remember' or "
                    "mode='update' so you can look this exact pattern up again later with "
                    "mode='find_pattern' — use this instead of recall's fuzzy similarity search when you "
                    "need to reliably recognize 'we've seen this before' rather than guess from a score. "
                    "Required for mode='find_pattern'."
                ),
            },
        },
        "required": ["mode"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        mode = str(arguments.get("mode", "")).strip().lower()
        write_tables, read_tables = self._resolve_grants(context)

        if mode == "remember":
            return await self._remember(arguments, context, write_tables)
        if mode == "recall":
            return await self._recall(arguments, context, read_tables)
        if mode == "update":
            return await self._update(arguments, context, write_tables)
        if mode == "forget":
            return await self._forget(arguments, context, write_tables)
        if mode == "find_pattern":
            return await self._find_pattern(arguments, context, read_tables)
        return {"error": f"Unsupported mode: {mode!r}."}

    @staticmethod
    def _is_write_allowed(table: str, write_tables: list[str]) -> bool:
        return "*" in write_tables or table in write_tables

    @staticmethod
    def _is_read_allowed(table: str, read_tables: list[str]) -> bool:
        return "*" in read_tables or table in read_tables

    def _resolve_grants(self, context: ToolContext) -> tuple[list[str], list[str]]:
        """Read this agent's write/read table grants from its own config only.

        Deliberately never looks at `arguments` — the LLM's tool-call payload is not a
        trusted source for access control. If any part of the chain down to the grant
        dict is missing or malformed, fail closed (return no tables).
        """
        agent_config = context.extra.get("agent_config") if isinstance(context.extra, dict) else None
        if not isinstance(agent_config, dict):
            return [], []

        tool_config = agent_config.get("tool_config")
        if not isinstance(tool_config, dict):
            return [], []

        forced_arguments = tool_config.get("forced_arguments")
        if not isinstance(forced_arguments, dict):
            return [], []

        grant = forced_arguments.get(self.name)
        if not isinstance(grant, dict):
            return [], []

        placeholders = build_agent_placeholder_values(
            agent_id=context.agent_id,
            agent_config=agent_config,
            broker_name=context.broker_name,
            pair=context.pair,
        )
        resolved = resolve_argument_templates(grant, placeholders)

        write_tables = resolved.get("write_tables")
        read_tables = resolved.get("read_tables")
        write_tables = list(write_tables) if isinstance(write_tables, list) else []
        read_tables = list(read_tables) if isinstance(read_tables, list) else []
        return write_tables, read_tables

    async def _remember(
        self, arguments: dict[str, Any], context: ToolContext, write_tables: list[str]
    ) -> Any:
        table = arguments.get("table")
        if not isinstance(table, str) or not table:
            return {"error": "Argument 'table' is required for mode='remember'."}
        if not self._is_write_allowed(table, write_tables):
            return {
                "error": (
                    f"No write access to table {table!r}. "
                    f"Granted write tables: {sorted(write_tables)}."
                )
            }

        text = arguments.get("text")
        if not isinstance(text, str) or not text.strip():
            return {"error": "Argument 'text' is required for mode='remember'."}

        tags = arguments.get("tags")
        if not isinstance(tags, list):
            tags = []

        importance = arguments.get("importance", 0.5)
        expiry_days = arguments.get("expiry_days")

        return await memory_request(
            context,
            "remember",
            {
                "table": table,
                "text": text,
                "agent_id": context.agent_id,
                "tags": tags,
                "importance": importance,
                "pair": context.pair or "",
                "broker": context.broker_name or "",
                "expiry_days": expiry_days,
                "pattern_key": arguments.get("pattern_key"),
            },
        )

    async def _recall(
        self, arguments: dict[str, Any], context: ToolContext, read_tables: list[str]
    ) -> Any:
        table = arguments.get("table")
        if isinstance(table, str) and table:
            if not self._is_read_allowed(table, read_tables):
                return {
                    "error": (
                        f"No read access to table {table!r}. "
                        f"Granted read tables: {sorted(read_tables)}."
                    )
                }
            tables = [table]
        else:
            if not read_tables:
                return {"error": "No read access granted to any table — nothing to search."}
            if "*" in read_tables:
                # Wildcard grant with no specific table requested: search every table
                # that currently exists (resolved fresh from the backend, not a fixed list).
                listing = await memory_request(context, "list_tables", {})
                tables = list(listing.get("tables", []))
                if not tables:
                    return {"results": []}
            else:
                tables = list(read_tables)

        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return {"error": "Argument 'query' is required for mode='recall'."}

        top_k = arguments.get("top_k", 5)

        return await memory_request(
            context,
            "recall",
            {
                "tables": tables,
                "query": query,
                "top_k": top_k,
                "candidate_pool": 50,
            },
        )

    async def _update(
        self, arguments: dict[str, Any], context: ToolContext, write_tables: list[str]
    ) -> Any:
        table = arguments.get("table")
        if not isinstance(table, str) or not table:
            return {"error": "Argument 'table' is required for mode='update'."}
        if not self._is_write_allowed(table, write_tables):
            return {
                "error": (
                    f"No write access to table {table!r}. "
                    f"Granted write tables: {sorted(write_tables)}."
                )
            }

        entry_id = arguments.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            return {"error": "Argument 'id' is required for mode='update'."}

        update_args: dict[str, Any] = {"table": table, "id": entry_id}
        if arguments.get("text") is not None:
            update_args["text"] = arguments["text"]
        if arguments.get("tags") is not None:
            update_args["tags"] = arguments["tags"]
        if arguments.get("importance") is not None:
            update_args["importance"] = arguments["importance"]
        if arguments.get("pattern_key") is not None:
            update_args["pattern_key"] = arguments["pattern_key"]

        return await memory_request(context, "update", update_args)

    async def _forget(
        self, arguments: dict[str, Any], context: ToolContext, write_tables: list[str]
    ) -> Any:
        table = arguments.get("table")
        if not isinstance(table, str) or not table:
            return {"error": "Argument 'table' is required for mode='forget'."}
        if not self._is_write_allowed(table, write_tables):
            return {
                "error": (
                    f"No write access to table {table!r}. "
                    f"Granted write tables: {sorted(write_tables)}."
                )
            }

        entry_id = arguments.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            return {"error": "Argument 'id' is required for mode='forget'."}

        return await memory_request(context, "forget", {"table": table, "id": entry_id})

    async def _find_pattern(
        self, arguments: dict[str, Any], context: ToolContext, read_tables: list[str]
    ) -> Any:
        pattern_key = arguments.get("pattern_key")
        if not isinstance(pattern_key, str) or not pattern_key.strip():
            return {"error": "Argument 'pattern_key' is required for mode='find_pattern'."}

        table = arguments.get("table")
        if isinstance(table, str) and table:
            if not self._is_read_allowed(table, read_tables):
                return {
                    "error": (
                        f"No read access to table {table!r}. "
                        f"Granted read tables: {sorted(read_tables)}."
                    )
                }
            tables = [table]
        else:
            if not read_tables:
                return {"error": "No read access granted to any table — nothing to search."}
            if "*" in read_tables:
                listing = await memory_request(context, "list_tables", {})
                tables = list(listing.get("tables", []))
                if not tables:
                    return {"found": False}
            else:
                tables = list(read_tables)

        return await memory_request(context, "find_pattern", {"tables": tables, "pattern_key": pattern_key})
