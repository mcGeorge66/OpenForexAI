from __future__ import annotations

import numpy as np

from openforexai.models.market import Candle
from openforexai.models.risk import CorrelationMatrix
from openforexai.utils.time_utils import utcnow


def compute_correlation_matrix(
    candle_sets: dict[str, list[Candle]],
) -> CorrelationMatrix:
    """Compute pairwise Pearson correlation of closing prices.

    *candle_sets* maps pair symbol → list of Candles (same timeframe, same length).
    Shorter series are padded by NaN and ignored in the correlation.
    """
    pairs = list(candle_sets)
    n = max(len(v) for v in candle_sets.values()) if candle_sets else 0

    # Align to a common length using the last n closes
    arrays: dict[str, np.ndarray] = {}
    for pair, candles in candle_sets.items():
        closes = np.array([float(c.close) for c in candles], dtype=float)
        if len(closes) < n:
            padded = np.full(n, np.nan)
            padded[n - len(closes) :] = closes
        else:
            padded = closes[-n:]
        arrays[pair] = padded

    matrix: dict[str, dict[str, float]] = {p: {} for p in pairs}
    for i, p1 in enumerate(pairs):
        for j, p2 in enumerate(pairs):
            if i == j:
                matrix[p1][p2] = 1.0
                continue
            a, b = arrays[p1], arrays[p2]
            mask = ~(np.isnan(a) | np.isnan(b))
            if mask.sum() < 2:
                matrix[p1][p2] = 0.0
            else:
                corr = float(np.corrcoef(a[mask], b[mask])[0, 1])
                matrix[p1][p2] = round(corr, 4)

    return CorrelationMatrix(
        pairs=pairs,
        matrix=matrix,
        computed_at=utcnow().isoformat(),
    )

