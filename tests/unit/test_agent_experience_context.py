from __future__ import annotations

from openforexai.agents.agent import Agent


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
