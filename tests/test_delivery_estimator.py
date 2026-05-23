"""配送日数推定のテスト.

Created: 2026-05-22
Updated: 2026-05-24 01:03
"""

from __future__ import annotations

from datetime import date, datetime

from src.models.customer import DeliveryLeadTime
from src.models.order import DeliveryRoute
from src.models.tenant import TenantConfig
from src.services.delivery_estimator import estimate, format_estimate


def _make_tenant(
    cutoff: int = 16,
    closed: list[int] | None = None,
    holidays: list[str] | None = None,
) -> TenantConfig:
    return TenantConfig(
        tenant_id="T-TEST",
        name="テスト社",
        order_cutoff_hour=cutoff,
        closed_weekdays=closed if closed is not None else [6],
        extra_holidays=holidays or [],
    )


class TestEstimateByRoute:
    def test_kanto_route(self):
        tc = _make_tenant(closed=[])
        min_d, max_d = estimate(
            DeliveryRoute.KANTO,
            date(2026, 5, 22),
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        assert min_d == date(2026, 5, 23)
        assert max_d == date(2026, 5, 23)

    def test_hokkaido_route(self):
        tc = _make_tenant(closed=[])
        min_d, max_d = estimate(
            DeliveryRoute.HOKKAIDO,
            date(2026, 5, 22),
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        assert min_d == date(2026, 5, 25)
        assert max_d == date(2026, 5, 25)

    def test_none_route_uses_default(self):
        tc = _make_tenant(closed=[])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        assert min_d == date(2026, 5, 24)
        assert max_d == date(2026, 5, 24)


class TestEstimateByLeadTime:
    def test_next_day_before_cutoff(self):
        tc = _make_tenant(cutoff=16, closed=[])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            lead_time=DeliveryLeadTime.NEXT_DAY,
            tenant_config=tc,
            now=datetime(2026, 5, 22, 15, 0),
        )
        assert min_d == date(2026, 5, 23)
        assert max_d == date(2026, 5, 23)

    def test_next_day_after_cutoff(self):
        tc = _make_tenant(cutoff=16, closed=[])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            lead_time=DeliveryLeadTime.NEXT_DAY,
            tenant_config=tc,
            now=datetime(2026, 5, 22, 17, 0),
        )
        # 締め後 → 起算日が翌日 → +1営業日 = 5/24
        assert min_d == date(2026, 5, 24)
        assert max_d == date(2026, 5, 24)

    def test_same_day_before_cutoff(self):
        tc = _make_tenant(cutoff=16, closed=[])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            lead_time=DeliveryLeadTime.SAME_DAY,
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        assert min_d == date(2026, 5, 22)
        assert max_d == date(2026, 5, 22)

    def test_one_day_gap(self):
        tc = _make_tenant(cutoff=16, closed=[])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            lead_time=DeliveryLeadTime.ONE_DAY_GAP,
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        # 中1日 = 2営業日後 → 5/24
        assert min_d == date(2026, 5, 24)
        assert max_d == date(2026, 5, 24)


class TestClosedDays:
    def test_skip_sunday(self):
        # 2026-05-22は金曜, 定休日=日曜(6)
        tc = _make_tenant(cutoff=16, closed=[6])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            lead_time=DeliveryLeadTime.ONE_DAY_GAP,
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        # 金曜起算 → 1営業日=土曜 → 2営業日=月曜(日曜スキップ)
        assert min_d == date(2026, 5, 25)

    def test_saturday_order_after_cutoff_skip_sunday(self):
        # 2026-05-23は土曜, 定休日=日曜(6)
        tc = _make_tenant(cutoff=16, closed=[6])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 23),
            lead_time=DeliveryLeadTime.NEXT_DAY,
            tenant_config=tc,
            now=datetime(2026, 5, 23, 17, 0),
        )
        # 締め後 → 起算日=日曜→月曜(日曜スキップ) → +1営業日=火曜
        assert min_d == date(2026, 5, 26)

    def test_extra_holiday(self):
        tc = _make_tenant(cutoff=16, closed=[], holidays=["2026-05-23"])
        min_d, max_d = estimate(
            None,
            date(2026, 5, 22),
            lead_time=DeliveryLeadTime.NEXT_DAY,
            tenant_config=tc,
            now=datetime(2026, 5, 22, 10, 0),
        )
        # 5/23が臨時休業 → スキップして5/24
        assert min_d == date(2026, 5, 24)


class TestFormatEstimate:
    def test_fixed_date_format(self):
        result = format_estimate(date(2026, 5, 23), date(2026, 5, 24))
        assert result == "5月23日配送予定"

    def test_same_date_format(self):
        result = format_estimate(date(2026, 5, 23), date(2026, 5, 23))
        assert result == "5月23日配送予定"

    def test_cross_month(self):
        result = format_estimate(date(2026, 5, 30), date(2026, 6, 2))
        assert result == "5月30日配送予定"
