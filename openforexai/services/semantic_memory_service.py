"""SemanticMemoryService — long-term, semantically searchable agent memory.

Bus member ``SYSTM-ALL___-GA-MEM``, processes MEMORY_REQUEST messages and
responds with MEMORY_RESPONSE — same shape as RepositoryService/REPO_REQUEST.

Backed by LanceDB (local, embedded, one directory per deployment, one table
per agent/shared scope) and BGE-M3 (BAAI) running fully locally via the
FlagEmbedding library — no network calls at request time. BGE-M3 produces
three representations per text (dense vector, sparse lexical weights, and a
multi-vector/ColBERT representation); all three are used: dense for fast
ANN recall, sparse+ColBERT to rerank that candidate set for precision.

``lancedb``/``FlagEmbedding``/``huggingface_hub`` are imported lazily inside
the methods that need them (not at module scope) so importing this module —
and anything that transitively imports it, e.g. bootstrap.py — never fails
just because those (large, optional-until-enabled) packages aren't installed
in a given environment. The service is only actually constructed when
``semantic_memory.enable`` is true in config.

Request payload::

    {"operation": "remember" | "recall" | "update" | "forget" | "list_tables" | "find_pattern", "args": {...}}

Response payload::

    {"operation": ..., "result": ..., "error": str | None}
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import perf_counter

import numpy as np
from pathlib import Path
from typing import Any
from uuid import uuid4

from openforexai.messaging.bus import EventBus
from openforexai.models.messaging import AgentMessage, EventType
from openforexai.utils.logging import get_logger

SEMANTIC_MEMORY_SERVICE_ID = "SYSTM-ALL___-GA-MEM"

_log = get_logger(__name__)

_TABLE_PREFIXES = ("mem_agent_", "mem_shared_")
_EMBEDDING_MODEL = "BAAI/bge-m3"
_DENSE_DIM = 1024

# ColBERT gives one _DENSE_DIM-wide vector per token, so a ~400-token memory is
# ~400k floats. Written as JSON text those were ~9 MB per row and cost ~0.19s per
# row just to parse back — with ~55 candidates per recall that was ~10s of pure
# parsing on every single analysis cycle. Stored as raw float32 bytes instead:
# ~1.6 MB per row and essentially free to load (np.frombuffer is a view, no
# per-number conversion). The readable `text` column is untouched and remains the
# source of truth — these vectors are derived data, regenerable from it at any time.
_COLBERT_BIN_FIELD = "colbert_bin"
_COLBERT_DTYPE = np.float32


def _pack_colbert(colbert: Any) -> bytes:
    """Serialize ColBERT token vectors to bytes: uint32 per-token dim, then float32 data.

    The dimension is stored in the blob itself rather than assumed to be
    _DENSE_DIM — otherwise a model whose ColBERT width differs (or ever changes)
    would silently reshape existing rows into garbage instead of failing loudly.
    """
    arr = np.asarray(colbert, dtype=_COLBERT_DTYPE)
    if arr.size == 0:
        return b""
    arr = np.atleast_2d(arr)
    dim = np.uint32(arr.shape[1]).tobytes()
    return dim + np.ascontiguousarray(arr).tobytes()


def _unpack_colbert(row: dict[str, Any]) -> Any:
    """Read a row's ColBERT vectors, preferring the binary column.

    Falls back to the legacy JSON column so rows written before the binary
    column existed keep working (slower, but correct) instead of silently
    scoring as "no match".
    """
    blob = row.get(_COLBERT_BIN_FIELD)
    if blob:
        dim = int(np.frombuffer(blob, dtype=np.uint32, count=1)[0])
        return np.frombuffer(blob, dtype=_COLBERT_DTYPE, offset=4).reshape(-1, dim)
    raw = row.get("colbert_vecs")
    return json.loads(raw) if raw else []

# BGE-M3's own commonly-recommended weighting for combining its three
# representations into one score — dense carries recall, sparse+colbert add
# precision on top of the dense-search candidate pool. Kept as named
# constants (not inlined) so this is easy to find and tune later.
_DENSE_WEIGHT = 0.4
_SPARSE_WEIGHT = 0.2
_COLBERT_WEIGHT = 0.4


def _is_valid_table_name(name: str) -> bool:
    return isinstance(name, str) and name.startswith(_TABLE_PREFIXES)


# ── Absolute-price-quote guard ──────────────────────────────────────────────
#
# The Examiner agent's own system prompt (config/system.json5, agent id
# OXS_T-ALL___-EA-EXAM) already instructs it, with a worked example, to
# describe prices/levels RELATIVELY (pips/ATR distance, position within a
# range, relative to a level) and never as absolute price quotes — an
# absolute price from a past trade is meaningless once the market has moved
# on. In practice the underlying LLM does not reliably follow that rule, so
# this is a code-level backstop: `remember()` rejects (ValueError) any text
# that looks like it contains an absolute FX price quote for the given pair.
#
# FX price quotes in this system fall into two clear magnitude/precision
# bands depending on quote convention (see DXY_COMPONENT_PAIRS in
# openforexai/adapters/brokers/base.py for the pair universe actually
# traded: EURUSD, USDJPY, GBPUSD, USDCAD, USDCHF):
#   - JPY-quote pairs (pair ends in "JPY"): ~50-400 magnitude, 2-3 decimals
#     (e.g. "159.765", "158.946", "158.15").
#   - Other majors (EURUSD, GBPUSD, USDCAD, USDCHF): ~0.3-3.0 magnitude,
#     4-5 decimals (e.g. "1.16812").
# If `pair` is empty/unrecognized, both bands are checked.
#
# This is deliberately fuzzy pattern-matching, not a parser: RSI values,
# Slope_S/ATR/confidence figures and similar indicator numbers routinely
# fall in the *same* magnitude/decimal range (e.g. RSI "60.87" looks exactly
# like a plausible USDJPY price) and must NOT be rejected. So a number in a
# price band is exempt when a unit or indicator label is *attached* to it —
# directly before ("RSI 60.87") or directly after ("63.50%", "0.63-mal").
#
# Attached, not nearby: an earlier version exempted the number whenever such
# a word appeared anywhere within 30 characters, and the Examiner's texts are
# dense with exactly those words. Three real price quotes reached the store
# that way, e.g. "per Stop bei 156.020 nach etwa zwei M5-Kerzen" (exempted by
# "Kerzen") and "bei 1,16270, rund 3,4 Pips" (exempted by "Pips").
#
# Both decimal separators are matched. The texts are German, and prices get
# written with a comma just as readily as with a dot — the two comma-written
# quotes above are the proof.

# The lookarounds only rule out matching *part* of a longer number
# ("1.234.567"); a trailing comma or full stop is punctuation, and excluding
# those let "…bei rund 1,16304, etwa 4,7 Pips…" through.
_PRICE_NUMBER_RE = re.compile(
    r"(?<!\w)(?<!\d[.,])\d{1,4}[.,]\d{2,5}(?!\w)(?![.,]\d)"
)

_JPY_PRICE_BAND = ((50.0, 400.0), (2, 3))       # (magnitude range, decimal-digits range)
_MAJOR_PRICE_BAND = ((0.3, 3.0), (4, 5))

# Indicator/metric name in front of the number, with only filler between them
# ("RSI 60.87", "RSI lag bei etwa 60.87", "Slope_S: 0.945").
_PRICE_LABEL_BEFORE_RE = re.compile(
    r"(?:rsi|slope_s|slope|atr|confidence|konfidenz|adx|macd|stoch)"
    r"(?:[\s:=-]*(?:lag|liegt|liegen|war|ist|betrug|beträgt|bei|von|mit|um|auf"
    r"|ca\.|circa|etwa|rund|about|at|of|was|is)\b){0,4}"
    r"[\s:=-]*$",
    re.IGNORECASE,
)
# Unit immediately after the number.
_PRICE_UNIT_AFTER_RE = re.compile(
    r"^\s*-?\s*(?:%|prozent|pips?|punkte?|points?|kerzen?|candles?|atr|mal|r\b)",
    re.IGNORECASE,
)
# Enough for the longest label plus its filler ("confidence lag bei etwa ").
_PRICE_LABEL_LOOKBACK = 40


def _price_bands_for_pair(pair: str) -> list[tuple[tuple[float, float], tuple[int, int]]]:
    pair = (pair or "").strip().upper()
    if not pair:
        return [_JPY_PRICE_BAND, _MAJOR_PRICE_BAND]
    if pair.endswith("JPY"):
        return [_JPY_PRICE_BAND]
    return [_MAJOR_PRICE_BAND]


def find_absolute_price_quotes(text: str, pair: str) -> list[str]:
    """Return the numbers in *text* that read as absolute price quotes for *pair*."""
    bands = _price_bands_for_pair(pair)
    found: list[str] = []
    for match in _PRICE_NUMBER_RE.finditer(text):
        number_str = match.group(0)
        magnitude = abs(float(number_str.replace(",", ".")))
        decimals = len(re.split(r"[.,]", number_str)[1])
        if not any(
            lo <= magnitude <= hi and dec_lo <= decimals <= dec_hi
            for (lo, hi), (dec_lo, dec_hi) in bands
        ):
            continue
        prefix = text[max(0, match.start() - _PRICE_LABEL_LOOKBACK):match.start()]
        if _PRICE_LABEL_BEFORE_RE.search(prefix):
            continue
        if _PRICE_UNIT_AFTER_RE.match(text[match.end():]):
            continue
        found.append(number_str)
    return found


def _reject_absolute_price_quotes(text: str, pair: str) -> None:
    """Raise ValueError if ``text`` looks like it names an absolute FX price
    for ``pair`` instead of describing it relatively. See module comment
    above for the heuristic."""
    for number_str in find_absolute_price_quotes(text, pair):
        pair_label = pair or "(unknown/unspecified)"
        raise ValueError(
            f"Memory text contains {number_str!r}, which looks like an absolute price "
            f"quote for pair {pair_label!r}, not a relative description. Rewrite this "
            "value in relative terms — pips/ATR distance, position within a range, or "
            "distance to a level — and never as an absolute price quote, since an "
            "absolute price from a past trade is meaningless once the market has moved "
            "on. Example: instead of 'Stop bei 158.946', write something like 'Stop etwa "
            "6 Pips unter dem Einstieg'."
        )


class SemanticMemoryService:
    """Processes MEMORY_REQUEST messages and responds with MEMORY_RESPONSE."""

    def __init__(
        self,
        lancedb_path: Path,
        embedding_device: str = "auto",
        embedding_use_fp16: bool = True,
        dense_candidate_pool: int = 50,
        default_top_k: int = 5,
        max_top_k: int = 20,
        bus: EventBus | None = None,
        monitoring_bus: Any = None,
    ) -> None:
        self._lancedb_path = lancedb_path
        self._embedding_device = embedding_device
        self._embedding_use_fp16 = embedding_use_fp16
        self._dense_candidate_pool = dense_candidate_pool
        self._default_top_k = default_top_k
        self._max_top_k = max_top_k
        self._bus = bus
        self._monitoring = monitoring_bus
        self._model: Any = None       # BGEM3FlagModel, loaded once in initialize()
        self._db: Any = None          # lancedb connection, opened once in initialize()
        self._table_locks: dict[str, asyncio.Lock] = {}
        self._inbox: asyncio.Queue[AgentMessage] | None = None
        if bus is not None:
            self._inbox = bus.register_member(SEMANTIC_MEMORY_SERVICE_ID)
        # Dedicated executor so a slow embed/LanceDB call only queues up behind
        # other semantic-memory work, never behind unrelated blocking calls
        # elsewhere in the process (MT5, config reads, ...) that happen to share
        # asyncio's single default ThreadPoolExecutor otherwise.
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="semantic-memory")

    async def _run_blocking(self, func, *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    # ── Construction / startup ────────────────────────────────────────────────

    @classmethod
    async def from_config(
        cls,
        memory_cfg: dict[str, Any],
        bus: EventBus,
        monitoring_bus: Any,
        project_root: Path,
    ) -> "SemanticMemoryService":
        lancedb_path_raw = str(memory_cfg.get("lancedb_path", "./data/semantic_memory"))
        lancedb_path = Path(lancedb_path_raw)
        if not lancedb_path.is_absolute():
            lancedb_path = (project_root / lancedb_path).resolve()

        embedding_cfg = memory_cfg.get("embedding", {})
        search_cfg = memory_cfg.get("search", {})

        service = cls(
            lancedb_path=lancedb_path,
            embedding_device=embedding_cfg.get("device", "auto"),
            embedding_use_fp16=bool(embedding_cfg.get("use_fp16", True)),
            dense_candidate_pool=int(search_cfg.get("dense_candidate_pool", 50)),
            default_top_k=int(search_cfg.get("default_top_k", 5)),
            max_top_k=int(search_cfg.get("max_top_k", 20)),
            bus=bus,
            monitoring_bus=monitoring_bus,
        )
        await service.initialize()
        return service

    async def initialize(self) -> None:
        """Provision the BGE-M3 model (downloading it first if missing) and open
        the LanceDB connection. Called once before the service accepts requests —
        the caller (bootstrap.py) awaits this before starting run(), so the first
        real agent request never has to wait for a multi-GB download."""
        await self._run_blocking(self._ensure_bge_m3_ready)
        self._lancedb_path.mkdir(parents=True, exist_ok=True)
        self._db = await self._run_blocking(self._connect_lancedb)
        _log.info("SemanticMemoryService initialized", lancedb_path=str(self._lancedb_path))

    def _connect_lancedb(self) -> Any:
        import lancedb
        return lancedb.connect(str(self._lancedb_path))

    def _ensure_bge_m3_ready(self) -> None:
        """Blocking: runs in this service's dedicated worker thread (see
        ``_run_blocking``). Loads the already-downloaded BGE-M3 model from the
        local cache, fully offline.

        Previously this contacted HuggingFace on every restart that didn't set
        OPENFOREXAI_SKIP_MODEL_CHECK (i.e. every manual restart) "to verify the
        cache is current", and — worse — relied on setting HF_HUB_OFFLINE /
        TRANSFORMERS_OFFLINE *after* that check to force offline mode for the
        rest of the process. Both parts were broken in production:

        1. huggingface_hub/transformers read these env vars once, at their own
           first import, and cache the result internally. By the time this
           method set them, `from huggingface_hub import snapshot_download`
           (a few lines below, in the old code) had already imported and
           cached "online" — setting the env var afterward changed nothing.
        2. Even setting them *before* any import, the "verify freshness"
           network call itself was the actual problem: on this deployment's
           network, HF Hub requests aren't actively refused, they're silently
           dropped — so every restart paid a multi-minute hang (repeatedly
           measured: 2-8 minutes) before falling through to the local files
           anyway, since they were already present and current. A real
           encode() call measured in isolation with offline mode forced from
           the very start took 0.43s — the model, the data, the CPU were
           never the problem.

        So: no network call here at all, ever, by default. HF_HUB_OFFLINE and
        TRANSFORMERS_OFFLINE are set FIRST, before any huggingface_hub/
        transformers/FlagEmbedding import — including the one below — so
        every library that reads them at its own import time sees "1". If the
        local cache is genuinely missing/incomplete, loading fails fast with a
        clear error instead of hanging; that's the correct failure mode, not
        a silent multi-minute stall on a background freshness check nobody
        asked for on every single restart.

        Set OPENFOREXAI_FORCE_MODEL_CHECK to explicitly opt into the old
        behavior (e.g. once, deliberately, after bumping the model version) —
        never automatically, and never as a restart default again.
        """
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        force_check = os.environ.get("OPENFOREXAI_FORCE_MODEL_CHECK", "").strip().lower() in {"1", "true", "yes", "on"}
        if force_check:
            _log.info(
                "OPENFOREXAI_FORCE_MODEL_CHECK set — contacting HuggingFace to verify "
                "the local BGE-M3 cache is current (this can take minutes).",
                model=_EMBEDDING_MODEL,
            )
            os.environ["HF_HUB_OFFLINE"] = "0"
            os.environ["TRANSFORMERS_OFFLINE"] = "0"
            from huggingface_hub import snapshot_download

            snapshot_download(repo_id=_EMBEDDING_MODEL)
            _log.info("BGE-M3 model weights verified against HuggingFace.")
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
        else:
            _log.info(
                "Loading BGE-M3 from local cache, fully offline (default — set "
                "OPENFOREXAI_FORCE_MODEL_CHECK=1 to verify against HuggingFace instead).",
                model=_EMBEDDING_MODEL,
            )

        from FlagEmbedding import BGEM3FlagModel

        device = None if self._embedding_device == "auto" else self._embedding_device
        _log.info("Loading BGE-M3 model...", device=self._embedding_device)
        self._model = BGEM3FlagModel(
            _EMBEDDING_MODEL,
            use_fp16=self._embedding_use_fp16,
            device=device,
        )
        _log.info("BGE-M3 model loaded.")

    # ── Embedding ──────────────────────────────────────────────────────────────

    async def _embed(self, text: str) -> dict[str, Any]:
        """Returns {"dense": [float]*1024, "sparse": {token_id_str: weight}, "colbert": [[float]*dim, ...]}."""
        return await self._run_blocking(self._embed_sync, text)

    def _embed_sync(self, text: str) -> dict[str, Any]:
        output = self._model.encode(
            [text], return_dense=True, return_sparse=True, return_colbert_vecs=True,
        )
        dense = output["dense_vecs"][0]
        sparse_raw = output["lexical_weights"][0]
        colbert_raw = output["colbert_vecs"][0]
        return {
            "dense": [float(x) for x in dense],
            "sparse": {str(k): float(v) for k, v in sparse_raw.items()},
            "colbert": [[float(x) for x in vec] for vec in colbert_raw],
        }

    # ── Scoring helpers (stage-2 rerank) ─────────────────────────────────────

    @staticmethod
    def _sparse_score(query_sparse: dict[str, float], doc_sparse: dict[str, float]) -> float:
        """Dot product over shared token ids — the standard lexical-matching score."""
        return sum(w * doc_sparse.get(tok, 0.0) for tok, w in query_sparse.items())

    @staticmethod
    def _colbert_score(query_vecs: list[list[float]], doc_vecs: list[list[float]]) -> float:
        """MaxSim late-interaction score: for each query token vector, take its max
        cosine similarity across all document token vectors, then average over
        query tokens — the standard ColBERT formula.

        Vectorized with numpy — the previous pure-Python nested-loop version (per-pair
        `sum(x*y for x,y in zip(...))` over ~400-token x1024-dim vectors) measured 127s
        for just 24 candidates in production (2026-09-11), which was the actual root
        cause of the multi-minute `recall()` latency, not model inference or LanceDB.
        This does the identical MaxSim-of-cosine-similarities math as one matrix
        multiply instead of Q*N*D scalar Python operations.
        """
        # len() rather than truthiness: doc_vecs is a numpy array when it comes
        # from the binary column, and `not array` raises on multi-element arrays.
        if query_vecs is None or doc_vecs is None or len(query_vecs) == 0 or len(doc_vecs) == 0:
            return 0.0

        q = np.asarray(query_vecs, dtype=np.float64)
        d = np.asarray(doc_vecs, dtype=np.float64)
        q_norm = np.linalg.norm(q, axis=1, keepdims=True)
        d_norm = np.linalg.norm(d, axis=1, keepdims=True)
        q_unit = np.divide(q, q_norm, out=np.zeros_like(q), where=q_norm != 0)
        d_unit = np.divide(d, d_norm, out=np.zeros_like(d), where=d_norm != 0)
        similarity = q_unit @ d_unit.T  # (num_query_tokens, num_doc_tokens) cosine sims
        return float(similarity.max(axis=1).mean())

    # ── LanceDB operations ────────────────────────────────────────────────────

    def _table_lock(self, table: str) -> asyncio.Lock:
        lock = self._table_locks.get(table)
        if lock is None:
            lock = asyncio.Lock()
            self._table_locks[table] = lock
        return lock

    def _table_schema(self) -> Any:
        import pyarrow as pa
        return pa.schema([
            pa.field("id", pa.string()),
            pa.field("agent_id", pa.string()),
            pa.field("created_at", pa.int64()),
            pa.field("created_at_iso", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), _DENSE_DIM)),
            pa.field("sparse_weights", pa.string()),   # JSON-encoded dict (small, ~4 KB)
            # Legacy JSON column — kept so pre-binary rows stay readable; new rows
            # write "" here and put the vectors in colbert_bin instead.
            pa.field("colbert_vecs", pa.string()),
            pa.field(_COLBERT_BIN_FIELD, pa.large_binary()),  # raw float32, (n_tokens, _DENSE_DIM)
            pa.field("tags", pa.list_(pa.string())),
            pa.field("importance", pa.float32()),
            pa.field("pair", pa.string()),
            pa.field("broker", pa.string()),
            pa.field("expiry_iso", pa.string()),
            pa.field("metadata_json", pa.string()),
            # Stable, exact-match key for a recurring setup/pattern type (assigned by the
            # writer, e.g. an Examiner agent) — lets a caller ask "have we seen this exact
            # pattern before?" via a precise filter instead of an imprecise similarity score.
            # Empty string (not null) when unset, to keep the LanceDB filter simple.
            pa.field("pattern_key", pa.string()),
        ])

    def _list_table_names(self) -> list[str]:
        return list(self._db.list_tables().tables)

    def _open_or_create_table_sync(self, table: str) -> Any:
        if table in self._list_table_names():
            tbl = self._db.open_table(table)
            self._ensure_colbert_bin_column(tbl)
            return tbl
        return self._db.create_table(table, schema=self._table_schema())

    @staticmethod
    def _ensure_colbert_bin_column(tbl: Any) -> None:
        """Add the binary ColBERT column to a table created before it existed.

        Without this, add() against a pre-migration table fails on schema
        mismatch — the service must not depend on a migration having been run.
        """
        if _COLBERT_BIN_FIELD in tbl.schema.names:
            return
        import pyarrow as pa
        tbl.add_columns(pa.field(_COLBERT_BIN_FIELD, pa.large_binary()))
        _log.info("Added binary ColBERT column to existing table", table=tbl.name)

    def _remember_sync(self, table: str, row: dict[str, Any]) -> None:
        tbl = self._open_or_create_table_sync(table)
        tbl.add([row])

    def _recall_one_table_sync(self, table: str, dense_vector: list[float], candidate_pool: int) -> list[dict[str, Any]]:
        if table not in self._list_table_names():
            return []
        tbl = self._db.open_table(table)
        results = tbl.search(dense_vector).limit(candidate_pool).to_list()
        for r in results:
            r["_table"] = table
        return results

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """Escape a value for embedding in a LanceDB/DataFusion SQL string filter."""
        return value.replace("'", "''")

    def _find_by_pattern_sync(self, table: str, pattern_key: str) -> dict[str, Any] | None:
        if table not in self._list_table_names():
            return None
        tbl = self._db.open_table(table)
        escaped = self._escape_filter_value(pattern_key)
        rows = tbl.search().where(f"pattern_key = '{escaped}'").limit(1).to_list()
        if not rows:
            return None
        row = rows[0]
        row["_table"] = table
        return row

    # ── Public operations ─────────────────────────────────────────────────────

    async def remember(self, args: dict[str, Any]) -> dict[str, Any]:
        table = args.get("table")
        if not _is_valid_table_name(table):
            raise ValueError(f"Invalid table name {table!r} — must start with 'mem_agent_' or 'mem_shared_'.")

        text = str(args["text"])
        _reject_absolute_price_quotes(text, str(args.get("pair", "")))
        embedding = await self._embed(text)

        expiry_days = args.get("expiry_days")
        expiry_iso = ""
        if expiry_days:
            from datetime import timedelta
            expiry_iso = (datetime.now(UTC) + timedelta(days=int(expiry_days))).isoformat()

        now = datetime.now(UTC)
        row = {
            "id": str(args["id"]) if args.get("id") else str(uuid4()),
            "agent_id": str(args.get("agent_id", "")),
            "created_at": int(now.timestamp()),
            "created_at_iso": now.isoformat(),
            "text": text,
            "vector": embedding["dense"],
            "sparse_weights": json.dumps(embedding["sparse"]),
            # Binary is the live format; the legacy JSON column stays empty rather
            # than duplicating ~9 MB per row that nothing reads.
            "colbert_vecs": "",
            _COLBERT_BIN_FIELD: _pack_colbert(embedding["colbert"]),
            "tags": [str(t) for t in (args.get("tags") or [])],
            "importance": float(args.get("importance", 0.5)),
            "pair": str(args.get("pair", "")),
            "broker": str(args.get("broker", "")),
            "expiry_iso": expiry_iso,
            "metadata_json": json.dumps(args.get("metadata", {})),
            "pattern_key": str(args.get("pattern_key") or ""),
        }

        async with self._table_lock(table):
            await self._run_blocking(self._remember_sync, table, row)

        return {"id": row["id"], "table": table}

    def _forget_sync(self, table: str, entry_id: str) -> bool:
        if table not in self._list_table_names():
            return False
        tbl = self._db.open_table(table)
        before = tbl.count_rows(f"id = '{entry_id}'")
        if before == 0:
            return False
        tbl.delete(f"id = '{entry_id}'")
        return True

    async def forget(self, args: dict[str, Any]) -> dict[str, Any]:
        table = args.get("table")
        if not _is_valid_table_name(table):
            raise ValueError(f"Invalid table name {table!r} — must start with 'mem_agent_' or 'mem_shared_'.")
        entry_id = str(args["id"])
        async with self._table_lock(table):
            deleted = await self._run_blocking(self._forget_sync, table, entry_id)
        return {"id": entry_id, "table": table, "deleted": deleted}

    async def update(self, args: dict[str, Any]) -> dict[str, Any]:
        """Modify an existing memory's text/tags/importance — implemented as delete +
        re-embed + re-insert (LanceDB has no in-place "re-vectorize" update), reusing the
        SAME id so external references to this memory stay valid across the edit."""
        table = args.get("table")
        if not _is_valid_table_name(table):
            raise ValueError(f"Invalid table name {table!r} — must start with 'mem_agent_' or 'mem_shared_'.")
        entry_id = str(args["id"])
        async with self._table_lock(table):
            existing_rows = await self._run_blocking(
                lambda: self._db.open_table(table).search().where(f"id = '{entry_id}'").limit(1).to_list()
                if table in self._list_table_names() else []
            )
            if not existing_rows:
                raise ValueError(f"No memory with id {entry_id!r} in table {table!r}.")
            existing = existing_rows[0]
            new_text = args.get("text")
            if new_text is None:
                new_text = existing.get("text", "")
            remember_args = {
                "id": entry_id,
                "table": table,
                "text": str(new_text),
                "agent_id": args.get("agent_id", existing.get("agent_id", "")),
                "tags": args.get("tags") if args.get("tags") is not None else list(existing.get("tags") or []),
                "importance": args.get("importance") if args.get("importance") is not None else float(existing.get("importance", 0.5)),
                "pair": existing.get("pair", ""),
                "broker": existing.get("broker", ""),
                "pattern_key": args.get("pattern_key") if args.get("pattern_key") is not None else existing.get("pattern_key", ""),
            }
            await self._run_blocking(self._forget_sync, table, entry_id)
        return await self.remember(remember_args)

    async def list_tables(self, args: dict[str, Any]) -> dict[str, Any]:
        names = await self._run_blocking(self._list_table_names)
        return {"tables": sorted(names)}

    async def find_pattern(self, args: dict[str, Any]) -> dict[str, Any]:
        """Exact-match lookup by pattern_key across one or more tables — the "have we seen
        this exact setup before?" primitive, deliberately separate from recall()'s fuzzy
        similarity search so a caller can rely on it deterministically instead of trusting a
        score threshold. Tables are checked in the given order; the first match wins."""
        tables = args.get("tables") or []
        if not isinstance(tables, list) or not tables:
            raise ValueError("'tables' must be a non-empty list.")
        for table in tables:
            if not _is_valid_table_name(table):
                raise ValueError(f"Invalid table name {table!r} — must start with 'mem_agent_' or 'mem_shared_'.")

        pattern_key = str(args.get("pattern_key") or "").strip()
        if not pattern_key:
            raise ValueError("'pattern_key' is required.")

        for table in tables:
            row = await self._run_blocking(self._find_by_pattern_sync, table, pattern_key)
            if row is not None:
                return {
                    "found": True,
                    "table": row["_table"],
                    "id": row.get("id", ""),
                    "text": row.get("text", ""),
                    "tags": list(row.get("tags") or []),
                    "importance": float(row.get("importance", 0.5)),
                    "pair": row.get("pair", ""),
                    "broker": row.get("broker", ""),
                    "created_at_iso": row.get("created_at_iso", ""),
                    "metadata_json": row.get("metadata_json", "{}"),
                    "pattern_key": row.get("pattern_key", ""),
                }
        return {"found": False}

    async def recall(self, args: dict[str, Any]) -> dict[str, Any]:
        tables = args.get("tables") or []
        if not isinstance(tables, list) or not tables:
            raise ValueError("'tables' must be a non-empty list.")
        for table in tables:
            if not _is_valid_table_name(table):
                raise ValueError(f"Invalid table name {table!r} — must start with 'mem_agent_' or 'mem_shared_'.")

        query = str(args["query"])
        top_k = int(args.get("top_k") or self._default_top_k)
        candidate_pool = int(args.get("candidate_pool") or self._dense_candidate_pool)
        if args.get("top_k") is not None:
            top_k = min(top_k, self._max_top_k)
        if args.get("candidate_pool") is not None:
            candidate_pool = min(candidate_pool, self._max_top_k * 10)

        _t0 = perf_counter()
        query_embedding = await self._embed(query)
        _embed_ms = round((perf_counter() - _t0) * 1000, 1)

        candidates: list[dict[str, Any]] = []
        _search_ms: dict[str, float] = {}
        for table in tables:
            _ts = perf_counter()
            rows = await self._run_blocking(
                self._recall_one_table_sync, table, query_embedding["dense"], candidate_pool,
            )
            _search_ms[table] = round((perf_counter() - _ts) * 1000, 1)
            candidates.extend(rows)

        _t_rerank = perf_counter()
        scored: list[dict[str, Any]] = []
        for row in candidates:
            doc_sparse = json.loads(row.get("sparse_weights") or "{}")
            doc_colbert = _unpack_colbert(row)
            dense_score = 1.0 - float(row.get("_distance", 0.0))  # LanceDB returns L2/cosine distance
            sparse_score = self._sparse_score(query_embedding["sparse"], doc_sparse)
            colbert_score = self._colbert_score(query_embedding["colbert"], doc_colbert)
            final_score = (
                _DENSE_WEIGHT * dense_score
                + _SPARSE_WEIGHT * sparse_score
                + _COLBERT_WEIGHT * colbert_score
            )
            scored.append({
                "table": row["_table"],
                "id": row.get("id", ""),
                "text": row.get("text", ""),
                "score": final_score,
                "tags": list(row.get("tags") or []),
                "importance": float(row.get("importance", 0.5)),
                "pair": row.get("pair", ""),
                "broker": row.get("broker", ""),
                "created_at_iso": row.get("created_at_iso", ""),
                "metadata_json": row.get("metadata_json", "{}"),
                "pattern_key": row.get("pattern_key", ""),
            })

        scored.sort(key=lambda r: r["score"], reverse=True)

        _rerank_ms = round((perf_counter() - _t_rerank) * 1000, 1)
        _total_ms = round((perf_counter() - _t0) * 1000, 1)
        if _total_ms > 2000:
            _log.warning(
                "Slow recall() — phase breakdown",
                total_ms=_total_ms, embed_ms=_embed_ms, search_ms=_search_ms,
                rerank_ms=_rerank_ms, candidate_count=len(candidates), tables=tables,
            )

        return {"results": scored[:top_k]}

    # ── Bus loop ───────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Process MEMORY_REQUEST messages until cancelled."""
        _log.info("SemanticMemoryService started", member_id=SEMANTIC_MEMORY_SERVICE_ID)
        while True:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if msg.event_type != EventType.MEMORY_REQUEST:
                continue

            await self._handle(msg)

    async def _handle(self, msg: AgentMessage) -> None:
        operation = msg.payload.get("operation", "")
        args = msg.payload.get("args", {})

        result: Any = None
        error: str | None = None
        _started = perf_counter()
        try:
            if operation == "remember":
                result = await self.remember(args)
            elif operation == "recall":
                result = await self.recall(args)
            elif operation == "forget":
                result = await self.forget(args)
            elif operation == "update":
                result = await self.update(args)
            elif operation == "list_tables":
                result = await self.list_tables(args)
            elif operation == "find_pattern":
                result = await self.find_pattern(args)
            else:
                raise ValueError(f"Unknown operation {operation!r}")
        except Exception as exc:
            error = str(exc)
            _log.error("SemanticMemoryService: operation '%s' failed: %s", operation, exc, exc_info=True)

        # Single-consumer queue (see run()) — one slow operation delays every request
        # queued behind it. Logged here (not just inside recall()) so any operation's
        # contribution to that queueing delay is visible, not just recall()'s own cost.
        elapsed_ms = round((perf_counter() - _started) * 1000, 1)
        if elapsed_ms > 2000:
            _log.warning(
                "Slow SemanticMemoryService operation — delays every request queued behind it",
                operation=operation, elapsed_ms=elapsed_ms, source=msg.source_agent_id,
            )

        await self._bus.publish(
            AgentMessage(
                event_type=EventType.MEMORY_RESPONSE,
                source_agent_id=SEMANTIC_MEMORY_SERVICE_ID,
                target_agent_id=msg.source_agent_id,
                payload={"operation": operation, "result": result, "error": error},
                correlation_id=str(msg.id),
            ),
            triggered_by=msg,
        )
