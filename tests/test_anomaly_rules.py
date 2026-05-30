"""anomaly_rules.classify_quantity_anomaly の境界値テスト。"""

from __future__ import annotations

import pytest

from src.models.intelligence import ProductStats
from src.services.anomaly_rules import (
    FALLBACK_QTY_THRESHOLD,
    MIN_PROFILE_ORDERS,
    classify_quantity_anomaly,
)


def _make_stats(avg: float, std: float, orders: int = 5, unit: str = "kg") -> ProductStats:
    return ProductStats(
        product_id="P-001",
        product_name="バナナ",
        total_orders=orders,
        avg_qty=avg,
        std_dev=std,
        typical_unit=unit,
    )


class TestNormalCases:
    def test_none_qty_returns_none(self):
        assert classify_quantity_anomaly(None, "kg", None) is None  # type: ignore[arg-type]

    def test_within_z_medium_returns_none(self):
        stats = _make_stats(avg=10, std=2)
        # z = |14 - 10| / 2 = 2.0 ≤ 3.0
        assert classify_quantity_anomaly(14.0, "kg", stats) is None

    def test_exactly_z_medium_returns_none(self):
        stats = _make_stats(avg=10, std=2)
        # z = |16 - 10| / 2 = 3.0 → 以下なので None
        assert classify_quantity_anomaly(16.0, "kg", stats) is None

    def test_no_profile_below_fallback_returns_none(self):
        assert classify_quantity_anomaly(99.0, "kg", None) is None

    def test_profile_orders_below_minimum_treated_as_no_profile(self):
        stats = _make_stats(avg=10, std=2, orders=MIN_PROFILE_ORDERS - 1)
        # orders < MIN → フォールバック判定。99 < 100 なので None
        assert classify_quantity_anomaly(99.0, "kg", stats) is None


class TestMediumSeverity:
    def test_z_above_medium_below_high_is_medium(self):
        stats = _make_stats(avg=10, std=2)
        # z = |18 - 10| / 2 = 4.0 > 3.0 かつ < 6.0
        result = classify_quantity_anomaly(18.0, "kg", stats)
        assert result is not None
        assert result["severity"] == "medium"
        assert result["z_score"] == pytest.approx(4.0)

    def test_std_zero_fixed_value_deviation_is_medium(self):
        stats = _make_stats(avg=10, std=0)
        result = classify_quantity_anomaly(15.0, "kg", stats)
        assert result is not None
        assert result["severity"] == "medium"
        assert result["z_score"] is None

    def test_std_zero_same_value_returns_none(self):
        stats = _make_stats(avg=10, std=0)
        assert classify_quantity_anomaly(10.0, "kg", stats) is None

    def test_fallback_at_threshold_is_medium(self):
        result = classify_quantity_anomaly(FALLBACK_QTY_THRESHOLD, "kg", None)
        assert result is not None
        assert result["severity"] == "medium"
        assert result["z_score"] is None

    def test_fallback_above_threshold_is_medium(self):
        result = classify_quantity_anomaly(200.0, "個", None)
        assert result is not None
        assert result["severity"] == "medium"


class TestHighSeverity:
    def test_z_exactly_high_threshold_is_high(self):
        stats = _make_stats(avg=10, std=2)
        # z = |22 - 10| / 2 = 6.0 >= Z_HIGH
        result = classify_quantity_anomaly(22.0, "kg", stats)
        assert result is not None
        assert result["severity"] == "high"
        assert result["z_score"] == pytest.approx(6.0)

    def test_z_above_high_threshold_is_high(self):
        stats = _make_stats(avg=10, std=2)
        # z = |100 - 10| / 2 = 45.0
        result = classify_quantity_anomaly(100.0, "kg", stats)
        assert result is not None
        assert result["severity"] == "high"

    def test_result_contains_summary_and_typical(self):
        stats = _make_stats(avg=10, std=2, unit="箱")
        result = classify_quantity_anomaly(22.0, "箱", stats)
        assert result is not None
        assert "summary" in result
        assert result["typical_qty"] == pytest.approx(10.0)
        assert result["typical_unit"] == "箱"
