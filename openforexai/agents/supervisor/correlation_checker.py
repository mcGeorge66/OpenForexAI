from __future__ import annotations

from openforexai.data.correlation import compute_correlation_matrix
from openforexai.models.market import Candle
from openforexai.models.risk import CorrelationMatrix


class CorrelationChecker:
    """Computes and caches the cross-pair correlation matrix."""

    def __init__(self) -> None:
        self._cached: CorrelationMatrix | None = None

    def update(self, candle_sets: dict[str, list[Candle]]) -> CorrelationMatrix:
        """Recompute and cache the matrix from the provided candle sets."""
        self._cached = compute_correlation_matrix(candle_sets)
        return self._cached

    @property
    def matrix(self) -> CorrelationMatrix | None:
        return self._cached
