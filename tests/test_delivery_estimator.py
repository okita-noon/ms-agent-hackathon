"""配送日数推定のテスト.

Created: 2026-05-22
Updated: 2026-05-22 21:13
"""

from __future__ import annotations

from datetime import date

from src.models.order import DeliveryRoute
from src.services.delivery_estimator import estimate, format_estimate


class TestEstimate:
    def test_kanto_route(self):
        min_d, max_d = estimate(DeliveryRoute.KANTO, date(2026, 5, 22))
        assert min_d == date(2026, 5, 23)
        assert max_d == date(2026, 5, 24)

    def test_hokkaido_route(self):
        min_d, max_d = estimate(DeliveryRoute.HOKKAIDO, date(2026, 5, 22))
        assert min_d == date(2026, 5, 25)
        assert max_d == date(2026, 5, 27)

    def test_okinawa_route(self):
        min_d, max_d = estimate(DeliveryRoute.OKINAWA, date(2026, 5, 22))
        assert min_d == date(2026, 5, 27)
        assert max_d == date(2026, 5, 29)

    def test_none_route_uses_default(self):
        min_d, max_d = estimate(None, date(2026, 5, 22))
        assert min_d == date(2026, 5, 24)
        assert max_d == date(2026, 5, 26)

    def test_no_order_date_uses_today(self):
        min_d, max_d = estimate(DeliveryRoute.KANTO)
        today = date.today()
        assert min_d > today
        assert max_d > today


class TestFormatEstimate:
    def test_range_format(self):
        result = format_estimate(date(2026, 5, 23), date(2026, 5, 24))
        assert result == "5月23日〜5月24日頃のお届け予定"

    def test_same_date_format(self):
        result = format_estimate(date(2026, 5, 23), date(2026, 5, 23))
        assert result == "5月23日頃のお届け予定"

    def test_cross_month(self):
        result = format_estimate(date(2026, 5, 30), date(2026, 6, 2))
        assert result == "5月30日〜6月2日頃のお届け予定"
