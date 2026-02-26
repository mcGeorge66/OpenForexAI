from __future__ import annotations

from tests.conftest import make_candle
from openforexai.data.correlation import compute_correlation_matrix


def test_self_correlation_is_one():
    candles = [make_candle(1.1000 + i * 0.0001) for i in range(30)]
    matrix = compute_correlation_matrix({"EURUSD": candles})
    assert matrix.matrix["EURUSD"]["EURUSD"] == 1.0


def test_two_pairs_correlation_range():
    eu = [make_candle(1.1000 + i * 0.0001) for i in range(30)]
    gu = [make_candle(1.2500 + i * 0.0001) for i in range(30)]
    matrix = compute_correlation_matrix({"EURUSD": eu, "GBPUSD": gu})
    corr = matrix.matrix["EURUSD"]["GBPUSD"]
    assert -1.0 <= corr <= 1.0


def test_empty_input():
    matrix = compute_correlation_matrix({})
    assert matrix.pairs == []
