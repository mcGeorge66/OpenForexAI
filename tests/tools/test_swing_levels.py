"""Unit tests for the touch_count logic in openforexai/tools/market/swing_levels.py.

`_cluster_levels` merges raw swing points whose prices lie within `min_gap` of
each other and stamps the merged cluster with `touch_count` = how many raw
points were merged in. `_detect_confluence` then looks for SH/SL pairs close
enough to call "confluence" and sums their two touch_counts. Both are pure
functions (no bus/ToolContext needed), so they're tested directly here.
"""
from __future__ import annotations

from openforexai.tools.market.swing_levels import _cluster_levels, _detect_confluence


def _level(price: float, ts: str = "2026-01-01T00:00:00Z", touch_count: int | None = None) -> dict:
    lv = {"price": price, "timestamp": ts, "distance": 0.0, "prominence": 0.0}
    if touch_count is not None:
        lv["touch_count"] = touch_count
    return lv


class TestClusterLevelsTouchCount:
    def test_isolated_peak_gets_touch_count_1(self):
        levels = [_level(1.1000)]
        result = _cluster_levels(levels, min_gap=0.0005, keep="max")
        assert len(result) == 1
        assert result[0]["touch_count"] == 1
        assert result[0]["price"] == 1.1000

    def test_multiple_isolated_peaks_stay_separate_with_touch_count_1(self):
        # Far enough apart (> min_gap) that none of them merge.
        levels = [_level(1.1000), _level(1.1050), _level(1.1100)]
        result = _cluster_levels(levels, min_gap=0.0005, keep="max")
        assert len(result) == 3
        assert all(lv["touch_count"] == 1 for lv in result)

    def test_nearby_peaks_cluster_with_summed_touch_count(self):
        # Three raw swing highs within min_gap of each other must merge into
        # a single cluster whose touch_count is the *count* of raw points
        # merged (3), not a sum of any pre-existing touch_count field.
        levels = [
            _level(1.1000, ts="2026-01-01T00:00:00Z"),
            _level(1.1003, ts="2026-01-01T01:00:00Z"),
            _level(1.1004, ts="2026-01-01T02:00:00Z"),  # most recent
        ]
        result = _cluster_levels(levels, min_gap=0.0005, keep="max")
        assert len(result) == 1
        assert result[0]["touch_count"] == 3
        # keep="max" retains the highest price in the cluster.
        assert result[0]["price"] == 1.1004
        # the most recent timestamp in the cluster is preserved.
        assert result[0]["timestamp"] == "2026-01-01T02:00:00Z"

    def test_cluster_keep_min_retains_lowest_price(self):
        levels = [
            _level(1.1000, ts="2026-01-01T00:00:00Z"),
            _level(1.0998, ts="2026-01-01T01:00:00Z"),
            _level(1.0999, ts="2026-01-01T02:00:00Z"),
        ]
        result = _cluster_levels(levels, min_gap=0.0005, keep="min")
        assert len(result) == 1
        assert result[0]["touch_count"] == 3
        assert result[0]["price"] == 1.0998

    def test_two_separate_clusters_each_get_own_touch_count(self):
        levels = [
            _level(1.1000), _level(1.1002), _level(1.1004),  # cluster A: 3 points
            _level(1.2000), _level(1.2001),                  # cluster B: 2 points
        ]
        result = _cluster_levels(levels, min_gap=0.0005, keep="max")
        assert len(result) == 2
        by_price = {round(lv["price"], 4): lv["touch_count"] for lv in result}
        assert by_price[1.1004] == 3
        assert by_price[1.2001] == 2

    def test_min_gap_zero_disables_clustering_each_gets_touch_count_1(self):
        levels = [_level(1.1000), _level(1.1001), _level(1.1002)]
        result = _cluster_levels(levels, min_gap=0.0, keep="max")
        assert len(result) == 3
        assert all(lv["touch_count"] == 1 for lv in result)

    def test_empty_input_returns_empty(self):
        assert _cluster_levels([], min_gap=0.0005, keep="max") == []


class TestConfluenceTouchCount:
    def test_confluence_sums_touch_count_from_both_high_and_low(self):
        # A swing-high cluster (touch_count=3) and a swing-low cluster
        # (touch_count=2) sitting within min_gap of each other must combine
        # into one confluence level whose touch_count is the sum (5).
        highs = [_level(1.1005, touch_count=3)]
        lows = [_level(1.1000, touch_count=2)]
        remaining_highs, remaining_lows, confluence = _detect_confluence(
            highs, lows, min_gap=0.001, current_price=1.1002,
        )
        assert remaining_highs == []
        assert remaining_lows == []
        assert len(confluence) == 1
        assert confluence[0]["touch_count"] == 5
        assert confluence[0]["price"] == round((1.1005 + 1.1000) / 2, 6)

    def test_confluence_defaults_missing_touch_count_to_1(self):
        # If a level dict has no touch_count at all (e.g. came straight from
        # raw peak detection, never clustered), _detect_confluence must treat
        # it as a single touch rather than raising.
        highs = [_level(1.1005)]
        lows = [_level(1.1000)]
        _, _, confluence = _detect_confluence(highs, lows, min_gap=0.001, current_price=1.1002)
        assert len(confluence) == 1
        assert confluence[0]["touch_count"] == 2

    def test_no_confluence_when_levels_too_far_apart(self):
        highs = [_level(1.2000, touch_count=5)]
        lows = [_level(1.1000, touch_count=5)]
        remaining_highs, remaining_lows, confluence = _detect_confluence(
            highs, lows, min_gap=0.001, current_price=1.15,
        )
        assert confluence == []
        assert len(remaining_highs) == 1
        assert len(remaining_lows) == 1

    def test_confluence_picks_closest_low_for_each_high(self):
        # Two candidate lows within range of one high -- the closer one
        # should be matched, and its touch_count (not the farther one's)
        # contributes to the sum.
        highs = [_level(1.1000, touch_count=4)]
        lows = [
            _level(1.0997, touch_count=10),  # farther
            _level(1.0999, touch_count=1),   # closer -> should be picked
        ]
        _, _, confluence = _detect_confluence(highs, lows, min_gap=0.0005, current_price=1.0998)
        assert len(confluence) == 1
        assert confluence[0]["touch_count"] == 5  # 4 + 1, not 4 + 10
