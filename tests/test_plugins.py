from __future__ import annotations

import pytest

from src.models.intelligence import CustomerOrderProfile, ProductStats
from src.plugins.intake_plugin import IntakePlugin, _normalize_expression
from src.plugins.exception_plugin import ExceptionPlugin


class TestNormalizeExpression:
    def test_fullwidth_to_halfwidth(self):
        assert _normalize_expression("ツナ缶１００ｇ") == "ツナ缶100g"

    def test_strips_spaces(self):
        assert _normalize_expression("  りんご  5 箱  ") == "りんご5箱"

    def test_fullwidth_spaces(self):
        assert _normalize_expression("りんご　５箱") == "りんご5箱"

    def test_lowercase(self):
        assert _normalize_expression("Apple") == "apple"


class TestIntakePlugin:
    @pytest.mark.asyncio
    async def test_lookup_customer_found(self, mock_tenant_ctx, sample_customer):
        repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        repo.find_by_identifier.return_value = sample_customer

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.lookup_customer("03-1234-5678")

        assert result["found"] is True
        assert result["id"] == "C-001"

    @pytest.mark.asyncio
    async def test_lookup_customer_not_found(self, mock_tenant_ctx):
        repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        repo.find_by_identifier.return_value = None

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.lookup_customer("unknown")

        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_lookup_by_line_id_found(self, mock_tenant_ctx, sample_customer):
        repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        repo.find_by_line_user_id.return_value = sample_customer

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.lookup_customer_by_line_id("U1234567890")

        assert result["found"] is True
        repo.find_by_line_user_id.assert_called_once_with("T-TEST", "U1234567890")

    @pytest.mark.asyncio
    async def test_normalize_product_found(self, mock_tenant_ctx, sample_product):
        master = mock_tenant_ctx.get_connector("IProductMaster")
        master.fuzzy_match.return_value = sample_product

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.normalize_product("リンゴ")

        assert result["found"] is True
        assert result["name"] == "りんご"

    @pytest.mark.asyncio
    async def test_normalize_product_not_found(self, mock_tenant_ctx):
        master = mock_tenant_ctx.get_connector("IProductMaster")
        master.fuzzy_match.return_value = None

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.normalize_product("存在しない商品")

        assert result["found"] is False

    @pytest.mark.asyncio
    async def test_resolve_with_pattern_hit(self, mock_tenant_ctx, sample_pattern):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = sample_pattern

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.resolve_with_pattern("C-001", "ツナ缶100g")

        assert result is not None
        assert result["confidence"] == 0.7
        assert result["needs_confirmation"] is True  # 0.7 < 0.9 threshold

    @pytest.mark.asyncio
    async def test_resolve_with_pattern_high_confidence(self, mock_tenant_ctx, sample_pattern):
        sample_pattern.confidence = 0.95
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = sample_pattern

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.resolve_with_pattern("C-001", "ツナ缶100g")

        assert result["needs_confirmation"] is False  # 0.95 >= 0.9

    @pytest.mark.asyncio
    async def test_resolve_with_pattern_miss(self, mock_tenant_ctx):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = None

        plugin = IntakePlugin(mock_tenant_ctx)
        result = await plugin.resolve_with_pattern("C-001", "新しい表現")

        assert result is None


class TestExceptionPlugin:
    @pytest.mark.asyncio
    async def test_quantity_anomaly_detected(self, mock_tenant_ctx, sample_profile):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = sample_profile

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_quantity_anomaly("C-001", "P-001", 150.0)

        assert result["is_anomaly"] is True
        assert result["z_score"] > 3.0

    @pytest.mark.asyncio
    async def test_quantity_normal(self, mock_tenant_ctx, sample_profile):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = sample_profile

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_quantity_anomaly("C-001", "P-001", 16.0)

        assert result["is_anomaly"] is False

    @pytest.mark.asyncio
    async def test_quantity_no_profile(self, mock_tenant_ctx):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = None

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_quantity_anomaly("C-999", "P-001", 100.0)

        assert result["is_anomaly"] is False
        assert result["reason"] == "プロファイルなし"

    @pytest.mark.asyncio
    async def test_quantity_insufficient_data(self, mock_tenant_ctx):
        profile = CustomerOrderProfile(
            tenant_id="T-TEST",
            customer_id="C-001",
            product_stats={
                "P-001": ProductStats(avg_qty=10, total_orders=2),
            },
        )
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = profile

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_quantity_anomaly("C-001", "P-001", 100.0)

        assert result["is_anomaly"] is False
        assert result["reason"] == "データ不足"

    @pytest.mark.asyncio
    async def test_quantity_zero_stddev(self, mock_tenant_ctx):
        profile = CustomerOrderProfile(
            tenant_id="T-TEST",
            customer_id="C-001",
            product_stats={
                "P-001": ProductStats(
                    avg_qty=10,
                    std_dev=0,
                    min_qty=10,
                    max_qty=10,
                    typical_unit="kg",
                    total_orders=5,
                ),
            },
        )
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = profile

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_quantity_anomaly("C-001", "P-001", 20.0)

        assert result["is_anomaly"] is True

    @pytest.mark.asyncio
    async def test_unit_anomaly_detected(self, mock_tenant_ctx, sample_profile):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = sample_profile

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_unit_anomaly("C-001", "P-001", "箱")

        assert result["is_anomaly"] is True
        assert result["typical_unit"] == "kg"

    @pytest.mark.asyncio
    async def test_unit_normal(self, mock_tenant_ctx, sample_profile):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = sample_profile

        plugin = ExceptionPlugin(mock_tenant_ctx)
        result = await plugin.detect_unit_anomaly("C-001", "P-001", "kg")

        assert result["is_anomaly"] is False
