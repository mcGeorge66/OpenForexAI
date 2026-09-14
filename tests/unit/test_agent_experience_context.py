from __future__ import annotations

import pytest

from openforexai.agents.agent import Agent, _EXPERIENCE_MAX_OBSERVATIONS


def test_extract_fomak_code_from_tool_outputs():
    snapshot = {"tool_outputs": {"fomak_m5": {"fomak": "4U3431S", "pair": "EURUSD"}}}
    assert Agent._extract_fomak_code(snapshot) == "4U3431S"


def test_extract_fomak_code_from_assembled_fallback():
    # PTJ's assembly_transform_script sets "assembled" to the same dict as
    # tool_outputs — make sure that path works too if "tool_outputs" is absent.
    snapshot = {"assembled": {"fomak_m5": {"fomak": "1N4124S"}}}
    assert Agent._extract_fomak_code(snapshot) == "1N4124S"


def test_extract_fomak_code_missing_block_returns_none():
    assert Agent._extract_fomak_code({"tool_outputs": {"rsi_h1": {"latest": 55}}}) is None


def test_extract_fomak_code_none_snapshot_returns_none():
    assert Agent._extract_fomak_code(None) is None


def test_extract_fomak_code_malformed_returns_none():
    assert Agent._extract_fomak_code({"tool_outputs": {"fomak_m5": "not-a-dict"}}) is None
    assert Agent._extract_fomak_code({"tool_outputs": "not-a-dict"}) is None
    assert Agent._extract_fomak_code({"tool_outputs": {"fomak_m5": {"fomak": ""}}}) is None


class _DummyAgentForPayloadExtraction:
    """_extract_fomak_code_from_payload is an instance method (calls self._parse_json_object) —
    exercise it through a minimal stand-in rather than constructing a full Agent."""
    _extract_fomak_code_from_payload = Agent._extract_fomak_code_from_payload
    _parse_json_object = staticmethod(Agent._parse_json_object)


def test_extract_fomak_code_from_payload_reads_bas_forwarded_aa_answer():
    dummy = _DummyAgentForPayloadExtraction()
    payload = {"response": '{"symbol": "EURUSD", "fomak": "4U3431S", "decision": "BIAS_LONG"}'}
    assert dummy._extract_fomak_code_from_payload(payload) == "4U3431S"


def test_extract_fomak_code_from_payload_missing_response_returns_none():
    dummy = _DummyAgentForPayloadExtraction()
    assert dummy._extract_fomak_code_from_payload({}) is None
    assert dummy._extract_fomak_code_from_payload(None) is None


def test_extract_fomak_code_from_payload_non_json_response_returns_none():
    dummy = _DummyAgentForPayloadExtraction()
    assert dummy._extract_fomak_code_from_payload({"response": "not json"}) is None


# ── Dates on the observations, newest first ──────────────────────────────────

def test_format_observation_date_shortens_an_iso_timestamp():
    assert Agent._format_observation_date("2026-09-12T14:23:07.412331") == "2026-09-12 14:23"
    assert Agent._format_observation_date("2026-09-12T14:23:07.412331Z") == "2026-09-12 14:23"


def test_format_observation_date_survives_unparseable_input():
    # An undated observation is still worth showing — it must not be dropped
    # and must not raise.
    assert Agent._format_observation_date(None) == ""
    assert Agent._format_observation_date("") == ""
    assert Agent._format_observation_date("kein datum") == "kein datum"


class _DummyAgentForExperienceBlock:
    """_build_experience_context_block needs only these four things from an
    Agent; a full instance would need a bus, a repository and a broker."""
    _build_experience_context_block = Agent._build_experience_context_block
    _extract_fomak_code = staticmethod(Agent._extract_fomak_code)
    _extract_fomak_code_from_payload = Agent._extract_fomak_code_from_payload
    _parse_json_object = staticmethod(Agent._parse_json_object)
    _format_observation_date = staticmethod(Agent._format_observation_date)
    agent_id = "OXS_T-USDJPY-AA-PTJ"
    _bus = None

    def __init__(self, tables):
        self._tables = tables

    async def _semantic_memory_read_tables(self):
        return self._tables


@pytest.mark.asyncio
async def test_experience_block_lists_every_observation_with_its_date(monkeypatch):
    """One observation per FOMAK was showing the agent a coin flip: several
    notes on the same market character can contradict each other, and that
    disagreement is the information that matters."""
    captured: dict[str, object] = {}

    async def fake_memory_request(context, op, args):
        captured[op] = args
        return {
            "found": True,
            "match_count": 3,
            "matches": [
                {"text": "Einstieg direkt am Trigger lief gut", "tags": ["win"],
                 "created_at_iso": "2026-09-13T09:41:02.100000"},
                {"text": "Zu früh eingestiegen, Kerze drehte", "tags": [],
                 "created_at_iso": "2026-09-11T15:02:44.900000"},
                {"text": "Stop zu eng hinter der Invalidierung", "tags": ["loss"],
                 "created_at_iso": "2026-09-08T11:17:00.000000"},
            ],
        }

    monkeypatch.setattr("openforexai.tools.base.memory_request", fake_memory_request)
    agent = _DummyAgentForExperienceBlock(["mem_agent_test"])
    block = await agent._build_experience_context_block(
        "USDJPY", {"tool_outputs": {"fomak_m5": {"fomak": "3D113S"}}},
    )

    assert captured["find_pattern"]["pattern_key"] == "USDJPY_3D113S"
    assert captured["find_pattern"]["limit"] == _EXPERIENCE_MAX_OBSERVATIONS
    assert "2026-09-13 09:41: Einstieg direkt am Trigger lief gut [win]" in block
    assert "2026-09-11 15:02: Zu früh eingestiegen" in block
    assert "2026-09-08 11:17: Stop zu eng" in block
    assert block.index("2026-09-13") < block.index("2026-09-08"), "jüngste zuerst"
    assert "FOMAK" in block, "der exakte Treffer muss benannt werden"


@pytest.mark.asyncio
async def test_experience_block_accepts_a_reply_without_matches(monkeypatch):
    """Backwards compatibility: a find_pattern answer carrying only the flat
    fields (no 'matches') must still produce the single observation."""
    async def fake_memory_request(context, op, args):
        return {"found": True, "text": "alte Antwortform", "tags": [],
                "created_at_iso": "2026-09-01T08:00:00"}

    monkeypatch.setattr("openforexai.tools.base.memory_request", fake_memory_request)
    agent = _DummyAgentForExperienceBlock(["mem_agent_test"])
    block = await agent._build_experience_context_block(
        "USDJPY", {"tool_outputs": {"fomak_m5": {"fomak": "3D113S"}}},
    )
    assert "2026-09-01 08:00: alte Antwortform" in block


@pytest.mark.asyncio
async def test_experience_block_stays_empty_without_read_grants(monkeypatch):
    agent = _DummyAgentForExperienceBlock([])
    assert await agent._build_experience_context_block("USDJPY", {}) == ""
