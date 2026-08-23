from __future__ import annotations

import asyncio

import numpy as np
import pytest

from openforexai.services.semantic_memory_service import SemanticMemoryService

_DENSE_DIM = 1024


class _FakeModel:
    """Deterministic stand-in for BGEM3FlagModel — same dict shape/keys as the
    real thing (dense_vecs/lexical_weights/colbert_vecs), so the service's own
    plumbing (embedding call -> row build -> LanceDB -> rerank) is exercised
    without downloading/running the actual multi-GB model in a unit test."""

    def encode(self, sentences, batch_size=None, max_length=None,
               return_dense=None, return_sparse=None, return_colbert_vecs=None, **kwargs):
        text = sentences[0]
        words = text.lower().split()
        # A crude but deterministic "embedding": hash each word into a few
        # dimensions so texts sharing words end up with non-zero dot products,
        # while still being cheap and fully offline.
        vec = np.zeros(_DENSE_DIM, dtype=np.float32)
        for w in words:
            vec[hash(w) % _DENSE_DIM] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        sparse = {str(hash(w) % 1000): 1.0 for w in words}
        colbert = [vec[:16].tolist() for _ in words] or [[0.0] * 16]
        return {
            "dense_vecs": np.array([vec]),
            "lexical_weights": [sparse],
            "colbert_vecs": [colbert],
        }


@pytest.fixture
def service(tmp_path):
    svc = SemanticMemoryService(lancedb_path=tmp_path / "semantic_memory")
    svc._model = _FakeModel()
    import lancedb
    svc._lancedb_path.mkdir(parents=True, exist_ok=True)
    svc._db = lancedb.connect(str(svc._lancedb_path))
    return svc


@pytest.mark.asyncio
async def test_remember_then_recall_round_trip(service):
    await service.remember({
        "table": "mem_agent_OXS_T-EURUSD-AA-ANLYS",
        "text": "EURUSD tends to fade breakouts right before the London open",
        "agent_id": "OXS_T-EURUSD-AA-ANLYS",
    })
    result = await service.recall({
        "tables": ["mem_agent_OXS_T-EURUSD-AA-ANLYS"],
        "query": "EURUSD breakouts near London open",
    })
    assert len(result["results"]) == 1
    assert "breakouts" in result["results"][0]["text"]
    assert result["results"][0]["score"] > 0


@pytest.mark.asyncio
async def test_recall_on_nonexistent_table_returns_empty_not_error(service):
    result = await service.recall({
        "tables": ["mem_agent_never_written_to"],
        "query": "anything",
    })
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_forget_deletes_and_recall_no_longer_finds_it(service):
    remembered = await service.remember({
        "table": "mem_agent_test", "text": "temporary note to delete", "agent_id": "a",
    })
    result = await service.forget({"table": "mem_agent_test", "id": remembered["id"]})
    assert result == {"id": remembered["id"], "table": "mem_agent_test", "deleted": True}
    recall = await service.recall({"tables": ["mem_agent_test"], "query": "temporary note"})
    assert recall["results"] == []


@pytest.mark.asyncio
async def test_forget_nonexistent_id_returns_deleted_false_not_error(service):
    result = await service.forget({"table": "mem_agent_test", "id": "does-not-exist"})
    assert result == {"id": "does-not-exist", "table": "mem_agent_test", "deleted": False}


@pytest.mark.asyncio
async def test_update_changes_text_keeps_same_id(service):
    remembered = await service.remember({
        "table": "mem_agent_test", "text": "original text", "agent_id": "a", "tags": ["x"],
    })
    updated = await service.update({
        "table": "mem_agent_test", "id": remembered["id"], "text": "corrected text",
    })
    assert updated["id"] == remembered["id"]
    recall = await service.recall({"tables": ["mem_agent_test"], "query": "corrected text"})
    assert len(recall["results"]) == 1
    assert recall["results"][0]["id"] == remembered["id"]
    assert recall["results"][0]["text"] == "corrected text"
    assert recall["results"][0]["tags"] == ["x"]  # preserved, not overwritten


@pytest.mark.asyncio
async def test_update_nonexistent_id_raises(service):
    with pytest.raises(ValueError):
        await service.update({"table": "mem_agent_test", "id": "does-not-exist", "text": "x"})


@pytest.mark.asyncio
async def test_list_tables_reflects_created_tables(service):
    await service.remember({"table": "mem_agent_alpha", "text": "x", "agent_id": "a"})
    await service.remember({"table": "mem_shared_beta", "text": "y", "agent_id": "a"})
    result = await service.list_tables({})
    assert set(result["tables"]) >= {"mem_agent_alpha", "mem_shared_beta"}


@pytest.mark.asyncio
async def test_invalid_table_name_rejected_on_remember(service):
    with pytest.raises(ValueError):
        await service.remember({"table": "not_a_valid_prefix", "text": "x", "agent_id": "a"})


@pytest.mark.asyncio
async def test_invalid_table_name_rejected_on_recall(service):
    with pytest.raises(ValueError):
        await service.recall({"tables": ["not_a_valid_prefix"], "query": "x"})


@pytest.mark.asyncio
async def test_pattern_key_round_trip_remember_then_find(service):
    remembered = await service.remember({
        "table": "mem_agent_test", "text": "first occurrence", "agent_id": "a",
        "pattern_key": "eurusd_h1_uptrend_resistance_rebound",
    })
    found = await service.find_pattern({
        "tables": ["mem_agent_test"], "pattern_key": "eurusd_h1_uptrend_resistance_rebound",
    })
    assert found["found"] is True
    assert found["id"] == remembered["id"]
    assert found["table"] == "mem_agent_test"
    assert found["text"] == "first occurrence"


@pytest.mark.asyncio
async def test_find_pattern_not_found_returns_found_false(service):
    result = await service.find_pattern({"tables": ["mem_agent_test"], "pattern_key": "never_seen"})
    assert result == {"found": False}


@pytest.mark.asyncio
async def test_find_pattern_checks_tables_in_order_first_match_wins(service):
    await service.remember({
        "table": "mem_agent_a", "text": "in table a", "agent_id": "a", "pattern_key": "shared_key",
    })
    result = await service.find_pattern({"tables": ["mem_agent_a", "mem_shared_b"], "pattern_key": "shared_key"})
    assert result["found"] is True
    assert result["table"] == "mem_agent_a"


@pytest.mark.asyncio
async def test_update_preserves_pattern_key_when_not_supplied(service):
    remembered = await service.remember({
        "table": "mem_agent_test", "text": "original", "agent_id": "a", "pattern_key": "my_pattern",
    })
    await service.update({"table": "mem_agent_test", "id": remembered["id"], "text": "updated text"})
    found = await service.find_pattern({"tables": ["mem_agent_test"], "pattern_key": "my_pattern"})
    assert found["found"] is True
    assert found["text"] == "updated text"


@pytest.mark.asyncio
async def test_find_pattern_requires_non_empty_tables(service):
    with pytest.raises(ValueError):
        await service.find_pattern({"tables": [], "pattern_key": "x"})


@pytest.mark.asyncio
async def test_find_pattern_requires_pattern_key(service):
    with pytest.raises(ValueError):
        await service.find_pattern({"tables": ["mem_agent_test"], "pattern_key": ""})


@pytest.mark.asyncio
async def test_concurrent_remember_to_new_table_does_not_crash(service):
    table = "mem_shared_mt5_oxs_t"
    await asyncio.gather(*[
        service.remember({"table": table, "text": f"note {i}", "agent_id": "a"})
        for i in range(5)
    ])
    result = await service.recall({"tables": [table], "query": "note"})
    assert len(result["results"]) == 5
