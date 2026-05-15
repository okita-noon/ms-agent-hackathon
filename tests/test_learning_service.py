from __future__ import annotations

import pytest

from src.models.intelligence import (
    CustomerOrderProfile,
    OrderPattern,
    ProductStats,
    ResolvedItem,
)
from src.services.learning_service import LearningService, _normalize_expression, _same_resolution


class TestNormalizeExpression:
    def test_basic(self):
        assert _normalize_expression("  ツナ缶　１００ｇ  ") == "ツナ缶100g"

    def test_lowercase(self):
        assert _normalize_expression("APPLE") == "apple"


class TestSameResolution:
    def test_same_items(self):
        a = [ResolvedItem(product_id="P-001", product_name="a", qty=1, unit="kg")]
        b = [ResolvedItem(product_id="P-001", product_name="a", qty=5, unit="箱")]
        assert _same_resolution(a, b) is True

    def test_different_items(self):
        a = [ResolvedItem(product_id="P-001", product_name="a", qty=1, unit="kg")]
        b = [ResolvedItem(product_id="P-002", product_name="b", qty=1, unit="kg")]
        assert _same_resolution(a, b) is False

    def test_multiple_items_order_independent(self):
        a = [
            ResolvedItem(product_id="P-001", product_name="a", qty=1, unit="kg"),
            ResolvedItem(product_id="P-002", product_name="b", qty=2, unit="個"),
        ]
        b = [
            ResolvedItem(product_id="P-002", product_name="b", qty=2, unit="個"),
            ResolvedItem(product_id="P-001", product_name="a", qty=1, unit="kg"),
        ]
        assert _same_resolution(a, b) is True


class TestLearningServiceRecordPattern:
    @pytest.mark.asyncio
    async def test_creates_new_pattern(self, mock_tenant_ctx):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = None
        created = OrderPattern(
            tenant_id="T-TEST",
            customer_id="C-001",
            type="single",
            input_expression="りんご5箱",
            input_expression_normalized="りんご5箱",
            resolved_items=[
                ResolvedItem(product_id="P-001", product_name="りんご", qty=5, unit="箱"),
            ],
            confidence=0.7,
            occurrence_count=1,
        )
        store.create_pattern.return_value = created

        svc = LearningService(mock_tenant_ctx)
        result = await svc.record_pattern(
            customer_id="C-001",
            input_expression="りんご5箱",
            resolved_items=[
                ResolvedItem(product_id="P-001", product_name="りんご", qty=5, unit="箱"),
            ],
        )

        store.create_pattern.assert_called_once()
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_updates_existing_pattern(self, mock_tenant_ctx, sample_pattern):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = sample_pattern
        store.update_pattern.return_value = sample_pattern

        svc = LearningService(mock_tenant_ctx)
        result = await svc.record_pattern(
            customer_id="C-001",
            input_expression="ツナ缶100g",
            resolved_items=[
                ResolvedItem(product_id="P-010", product_name="ツナ缶", qty=1, unit="個"),
            ],
        )

        store.update_pattern.assert_called_once()
        assert abs(sample_pattern.confidence - 0.8) < 1e-9
        assert sample_pattern.occurrence_count == 3  # 2 + 1

    @pytest.mark.asyncio
    async def test_agent_inferred_lower_confidence(self, mock_tenant_ctx):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = None
        store.create_pattern.side_effect = lambda p: p

        svc = LearningService(mock_tenant_ctx)
        result = await svc.record_pattern(
            customer_id="C-001",
            input_expression="テスト",
            resolved_items=[
                ResolvedItem(product_id="P-001", product_name="test", qty=1, unit="個"),
            ],
            source="agent_inferred",
        )

        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_multi_item_creates_template(self, mock_tenant_ctx):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = None
        store.create_pattern.side_effect = lambda p: p

        svc = LearningService(mock_tenant_ctx)
        result = await svc.record_pattern(
            customer_id="C-001",
            input_expression="いつもの",
            resolved_items=[
                ResolvedItem(product_id="P-001", product_name="a", qty=1, unit="箱"),
                ResolvedItem(product_id="P-002", product_name="b", qty=2, unit="kg"),
            ],
        )

        assert result.type == "template"


class TestLearningServiceUpdateProfile:
    @pytest.mark.asyncio
    async def test_creates_new_profile(self, mock_tenant_ctx):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = None
        store.upsert_profile.side_effect = lambda p: p

        svc = LearningService(mock_tenant_ctx)
        result = await svc.update_customer_profile("C-001", "P-001", 10.0, "kg")

        assert "P-001" in result.product_stats
        stats = result.product_stats["P-001"]
        assert stats.avg_qty == 10.0
        assert stats.total_orders == 1
        assert stats.typical_unit == "kg"

    @pytest.mark.asyncio
    async def test_updates_existing_profile(self, mock_tenant_ctx, sample_profile):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = sample_profile
        store.upsert_profile.side_effect = lambda p: p

        svc = LearningService(mock_tenant_ctx)
        result = await svc.update_customer_profile("C-001", "P-001", 20.0, "kg")

        stats = result.product_stats["P-001"]
        assert stats.total_orders == 11
        expected_avg = (15.0 * 10 + 20.0) / 11
        assert abs(stats.avg_qty - expected_avg) < 0.01
        assert stats.max_qty == 30.0  # unchanged, 20 < 30
