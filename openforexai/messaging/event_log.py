"""Persistent event log — writes every AgentMessage to data/event_log.db.

Design constraints
------------------
- Direct sqlite3 via thread-pool executor — NEVER via RepositoryService to
  avoid circular event loops.
- Called from bus._persist_event() via asyncio.ensure_future() — fire-and-forget,
  never blocks the dispatch loop.
- Payloads > _COMPRESS_THRESHOLD bytes are zlib-compressed; is_compressed flag
  is set so readers can transparently decompress.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import zlib
from datetime import timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openforexai.models.messaging import AgentMessage

_log = logging.getLogger(__name__)

_DB_PATH = Path("data/event_log.db")
_COMPRESS_THRESHOLD = 8 * 1024  # 8 KB
_utc_offset: int = 0  # set by configure() at startup


def configure(utc_offset: int) -> None:
    global _utc_offset
    _utc_offset = utc_offset

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id                TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    source_agent      TEXT NOT NULL,
    target_agent      TEXT,
    correlation       TEXT,
    chain             TEXT NOT NULL DEFAULT '[]',
    payload           BLOB NOT NULL,
    is_compressed     INTEGER NOT NULL DEFAULT 0,
    is_trace_root     INTEGER NOT NULL DEFAULT 0,
    descendant_count  INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ev_event_type   ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_ev_source       ON events (source_agent);
CREATE INDEX IF NOT EXISTS idx_ev_created_at   ON events (created_at);
CREATE INDEX IF NOT EXISTS idx_ev_correlation  ON events (correlation);
CREATE INDEX IF NOT EXISTS idx_ev_trace_root   ON events (is_trace_root);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.executescript(_DDL)
    if not _column_exists(conn, "events", "is_trace_root"):
        conn.execute("ALTER TABLE events ADD COLUMN is_trace_root INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_trace_root ON events (is_trace_root)")
        conn.commit()
    if not _column_exists(conn, "events", "descendant_count"):
        conn.execute("ALTER TABLE events ADD COLUMN descendant_count INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    return conn


def _write_sync(row: dict) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO events
                (id, event_type, source_agent, target_agent, correlation,
                 chain, payload, is_compressed, is_trace_root, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["id"],
                row["event_type"],
                row["source_agent"],
                row["target_agent"],
                row["correlation"],
                row["chain"],
                row["payload"],
                row["is_compressed"],
                row["is_trace_root"],
                row["created_at"],
            ),
        )
        # Increment descendant_count on the root event (chain[0]) for every non-root event
        chain_ids: list = json.loads(row["chain"]) if isinstance(row["chain"], str) else row["chain"]
        if chain_ids:
            conn.execute(
                "UPDATE events SET descendant_count = descendant_count + 1 WHERE id = ?",
                (chain_ids[0],),
            )
        conn.commit()
    except Exception as exc:
        _log.error("event_log write failed for %s: %s", row.get("id"), exc)
    finally:
        conn.close()


async def persist_event(message: AgentMessage, *, is_trace_root: bool = False) -> None:
    """Serialize and persist one AgentMessage.  Fire-and-forget from the bus."""
    try:
        payload_bytes = json.dumps(message.payload, default=str).encode("utf-8")
        is_compressed = False
        if len(payload_bytes) > _COMPRESS_THRESHOLD:
            payload_bytes = zlib.compress(payload_bytes, level=6)
            is_compressed = True

        row = {
            "id": str(message.id),
            "event_type": str(message.event_type),
            "source_agent": message.source_agent_id,
            "target_agent": message.target_agent_id,
            "correlation": message.correlation_id,
            "chain": json.dumps([str(u) for u in message.chain]),
            "payload": payload_bytes,
            "is_compressed": int(is_compressed),
            "is_trace_root": int(is_trace_root),
            "created_at": message.created_at.astimezone(
                timezone(timedelta(hours=_utc_offset))
            ).isoformat(),
        }
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_sync, row)
    except Exception as exc:
        _log.error("persist_event failed for %s: %s", message.id, exc)


def read_event(event_id: str) -> dict | None:
    """Read a single event by ID (synchronous — for API use)."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(conn, row)
    finally:
        conn.close()


def read_events(
    *,
    event_type: str | None = None,
    source_agent: str | None = None,
    correlation: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    trace_roots_only: bool = False,
    chain_min: int | None = None,
    chain_max: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Query the event log with optional filters (synchronous — for API use)."""
    conn = _get_conn()
    try:
        clauses: list[str] = []
        params: list = []
        if trace_roots_only and _column_exists(conn, "events", "is_trace_root"):
            clauses.append("is_trace_root = 1")
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if source_agent:
            clauses.append("source_agent LIKE ?")
            params.append(f"%{source_agent}%")
        if correlation:
            clauses.append("correlation = ?")
            params.append(correlation)
        if from_time:
            clauses.append("created_at >= ?")
            params.append(from_time)
        if to_time:
            clauses.append("created_at <= ?")
            params.append(to_time)
        if chain_min is not None:
            clauses.append("descendant_count >= ?")
            params.append(chain_min)
        if chain_max is not None:
            clauses.append("descendant_count <= ?")
            params.append(chain_max)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = conn.execute(
            f"SELECT * FROM events {where} ORDER BY created_at DESC, json_array_length(chain) ASC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return [_row_to_dict_cols(cols, r) for r in rows]
    finally:
        conn.close()


def read_trace(event_id: str) -> list[dict]:
    """Return the full trace for event_id: ancestors + the event + all descendants, ordered by created_at."""
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        cols = [d[0] for d in cur.description]
        root_row = cur.fetchone()
        if root_row is None:
            return []

        event_dict = _row_to_dict_cols(cols, root_row)
        seen_ids: set[str] = {event_id}
        result: list[dict] = [event_dict]

        # 1. Load ancestors (IDs stored in chain field, oldest first)
        ancestor_ids: list[str] = event_dict.get("chain") or []
        if ancestor_ids:
            placeholders = ",".join("?" * len(ancestor_ids))
            anc_rows = conn.execute(
                f"SELECT * FROM events WHERE id IN ({placeholders})", ancestor_ids
            ).fetchall()
            anc_by_id = {r[0]: _row_to_dict_cols(cols, r) for r in anc_rows}
            for anc_id in ancestor_ids:
                if anc_id in anc_by_id and anc_id not in seen_ids:
                    seen_ids.add(anc_id)
                    result.append(anc_by_id[anc_id])

        # 2. Load all descendants iteratively
        frontier: list[str] = [event_id]
        while frontier:
            like_clauses = " OR ".join(["chain LIKE ?" for _ in frontier])
            excl = ",".join("?" * len(seen_ids))
            like_params = [f"%{fid}%" for fid in frontier]
            desc_rows = conn.execute(
                f"SELECT * FROM events WHERE ({like_clauses}) AND id NOT IN ({excl})"
                f" ORDER BY created_at ASC",
                like_params + list(seen_ids),
            ).fetchall()
            frontier = []
            for row in desc_rows:
                d = _row_to_dict_cols(cols, row)
                rid = d["id"]
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    result.append(d)
                    frontier.append(rid)

        result.sort(key=lambda d: d.get("created_at") or "")
        return result
    finally:
        conn.close()


def _row_to_dict(conn: sqlite3.Connection, row: tuple) -> dict:
    cur = conn.execute("SELECT * FROM events LIMIT 0")
    cols = [d[0] for d in cur.description]
    return _row_to_dict_cols(cols, row)


def _row_to_dict_cols(cols: list[str], row: tuple) -> dict:
    d = dict(zip(cols, row))
    # decompress payload
    payload_raw = d.get("payload", b"")
    is_compressed = bool(d.get("is_compressed", 0))
    try:
        if is_compressed and isinstance(payload_raw, (bytes, bytearray)):
            payload_raw = zlib.decompress(payload_raw)
        if isinstance(payload_raw, (bytes, bytearray)):
            d["payload"] = json.loads(payload_raw.decode("utf-8"))
        else:
            d["payload"] = payload_raw
    except Exception:
        d["payload"] = {}
    # chain as list
    try:
        d["chain"] = json.loads(d.get("chain") or "[]")
    except Exception:
        d["chain"] = []
    return d
