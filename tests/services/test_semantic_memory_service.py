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
async def test_remember_rejects_text_full_of_absolute_price_quotes(service):
    # Real (anonymized) Examiner output that mixes legitimate relative language
    # ("70 Pips", "11R", "rund 6 Pips") with leftover absolute USDJPY levels —
    # exactly the pattern the guard must catch.
    text = (
        "Pattern: USDJPY_3D2131S\n"
        "Trade-Date: 2026-09-02\n"
        "Observation: Zum Entry lag ein bärischer H1-Kontext vor: Nach einem "
        "Rückgang von etwa 159.90 in den Bereich 159.62/159.59 folgte ein "
        "begrenzter Rebound unter dem im Snapshot genannten Widerstand um "
        "159.765. Der M5-Trigger schloss bei etwa 159.701; der Short wurde als "
        "Market-Order bei etwa 159.651 ausgeführt, rund 5 Pips günstiger für die "
        "Short-Richtung. Die Analyse nannte einen Stop um 159.765 und ein Ziel um "
        "159.494. Im gespeicherten Order-Datensatz steht später jedoch ein Stop "
        "bei 158.946 und kein Take-Profit. Danach fiel USDJPY in wenigen "
        "M5-Kerzen bis etwa 158.15 und bewegte sich anschließend wieder nach "
        "oben; der Trade wurde laut Broker-Synchronisierung bei etwa 158.946 per "
        "Stop geschlossen.\n"
        "Outcome: Der Short endete mit einem realisierten Gewinn von rund 70 "
        "Pips beziehungsweise etwa 11R gemessen am ursprünglichen Risiko von "
        "rund 6 Pips.\n"
        "Evidence status: single_observation"
    )
    with pytest.raises(ValueError):
        await service.remember({
            "table": "mem_agent_test", "text": text, "agent_id": "a", "pair": "USDJPY",
        })


@pytest.mark.asyncio
async def test_remember_accepts_prompt_richtig_example_with_relative_language(service):
    # The EA system prompt's own "Richtig" (correct) worked example — must
    # keep working verbatim, otherwise the guard would contradict the prompt
    # it is meant to enforce.
    text = (
        "Der Trade wurde per Stop geschlossen, etwa 1,6 Pips gegen die Position "
        "vom Einstieg entfernt und näher am gebrochenen Level als die im "
        "Snapshot vorgesehene Stop-Distanz — ein kleiner Verlust nahe am "
        "Einstieg."
    )
    result = await service.remember({
        "table": "mem_agent_test", "text": text, "agent_id": "a", "pair": "USDJPY",
    })
    assert result["table"] == "mem_agent_test"


@pytest.mark.asyncio
async def test_remember_accepts_indicator_values_that_resemble_prices(service):
    # RSI/Slope_S values routinely fall in the same magnitude/decimal range as
    # real USDJPY prices (e.g. "60.87") — these must not be mistaken for
    # absolute price quotes just because of nearby-keyword exemptions.
    text = (
        "RSI lag bei etwa 60.87 und Slope_S bei 0.945, beide im positiven "
        "Bereich. Dies war die 4. beobachtete Situation dieses Patterns; 3 von "
        "4 Trades endeten profitabel, mit einem Ergebnis von rund 11R."
    )
    result = await service.remember({
        "table": "mem_agent_test", "text": text, "agent_id": "a", "pair": "USDJPY",
    })
    assert result["table"] == "mem_agent_test"


@pytest.mark.asyncio
async def test_remember_accepts_plain_text_with_no_numbers(service):
    result = await service.remember({
        "table": "mem_agent_test",
        "text": "EURUSD tends to fade breakouts right before the London open",
        "agent_id": "a",
    })
    assert result["table"] == "mem_agent_test"


@pytest.mark.asyncio
async def test_remember_checks_both_bands_when_pair_missing(service):
    # No 'pair' given (broker-shared note not tied to one pair) — both the
    # JPY-style and major-pair-style price bands must be checked, not skipped.
    jpy_style_text = "Der Kurs bewegte sich bis auf 158.15 zurück."
    with pytest.raises(ValueError):
        await service.remember({"table": "mem_shared_test", "text": jpy_style_text, "agent_id": "a"})

    major_style_text = "Der Kurs bewegte sich bis auf 1.16812 zurück."
    with pytest.raises(ValueError):
        await service.remember({"table": "mem_shared_test", "text": major_style_text, "agent_id": "a"})


@pytest.mark.asyncio
async def test_remember_pair_missing_does_not_reject_indicator_values(service):
    # Sanity check that the empty-pair fallback (checking both bands) does not
    # become overly aggressive: indicator values must still be exempt.
    text = "RSI lag bei etwa 60.87, ATR bei 0.945."
    result = await service.remember({"table": "mem_shared_test", "text": text, "agent_id": "a"})
    assert result["table"] == "mem_shared_test"


@pytest.mark.asyncio
async def test_concurrent_remember_to_new_table_does_not_crash(service):
    table = "mem_shared_mt5_oxs_t"
    await asyncio.gather(*[
        service.remember({"table": table, "text": f"note {i}", "agent_id": "a"})
        for i in range(5)
    ])
    result = await service.recall({"tables": [table], "query": "note"})
    assert len(result["results"]) == 5
