from __future__ import annotations

from datetime import date, datetime

import pytest

from src.models.order import (
    DeliveryCarrier,
    DeliveryRoute,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    TemperatureZone,
)
from src.models.customer import Customer, CustomerDeliveryPreference
from src.models.product import Product, UnitType
from src.models.intelligence import CustomerOrderProfile, OrderPattern, ProductStats, ResolvedItem
from src.models.session import OrderSession
from src.models.tenant import ConnectorConfig, TenantConfig


class TestOrderModel:
    def test_create_order(self):
        order = Order(
            uid="ORD-001",
            tenant_id="T-001",
            order_date=date(2026, 5, 16),
            customer_id="C-001",
            customer_name="テスト社",
            source=OrderSource.LINE,
            items=[
                OrderItem(
                    product_id="P-001",
                    product_name="りんご",
                    quantity=10,
                    unit="箱",
                    temperature_zone=TemperatureZone.CHILLED,
                ),
            ],
        )
        assert order.id == "ORD-001"
        assert order.status == OrderStatus.PENDING
        assert len(order.items) == 1
        assert order.items[0].quantity == 10

    def test_order_serialization(self):
        order = Order(
            uid="ORD-002",
            tenant_id="T-001",
            order_date=date(2026, 5, 16),
            customer_id="C-001",
            customer_name="テスト",
            source=OrderSource.PHONE,
        )
        data = order.model_dump(mode="json")
        assert data["tenant_id"] == "T-001"
        assert data["source"] == "Phone"

    def test_order_status_enum(self):
        assert OrderStatus.PENDING == "未処理"
        assert OrderStatus.COMPLETED == "完了"
        assert OrderStatus.AWAITING_REPLY == "返信待ち"

    def test_temperature_zone_enum(self):
        assert TemperatureZone.AMBIENT == "常温"
        assert TemperatureZone.CHILLED == "冷蔵"
        assert TemperatureZone.FROZEN == "冷凍"


class TestCustomerModel:
    def test_create_customer(self, sample_customer):
        assert sample_customer.id == "C-001"
        assert sample_customer.name == "株式会社テスト"
        assert sample_customer.active is True

    def test_customer_without_optional_fields(self):
        c = Customer(id="C-002", tenant_id="T-001", name="最小顧客")
        assert c.line_user_id is None
        assert c.email is None
        assert c.delivery_preference is not None  # has default


class TestProductModel:
    def test_create_product(self, sample_product):
        assert sample_product.id == "P-001"
        assert sample_product.default_unit == UnitType.BOX

    def test_unit_type_enum(self):
        assert UnitType.KG == "kg"
        assert UnitType.BOX == "箱"
        assert UnitType.PIECE == "個"
        assert UnitType.PACK == "パック"


class TestIntelligenceModels:
    def test_order_pattern(self, sample_pattern):
        assert sample_pattern.confidence == 0.7
        assert len(sample_pattern.resolved_items) == 1
        assert sample_pattern.resolved_items[0].product_id == "P-010"

    def test_product_stats_defaults(self):
        stats = ProductStats()
        assert stats.avg_qty == 0.0
        assert stats.total_orders == 0

    def test_customer_profile(self, sample_profile):
        assert "P-001" in sample_profile.product_stats
        stats = sample_profile.product_stats["P-001"]
        assert stats.avg_qty == 15.0
        assert stats.total_orders == 10


class TestSessionModel:
    def test_create_session(self):
        session = OrderSession(
            id="sess-001",
            tenant_id="T-001",
            channel="line",
            channel_user_id="U123",
        )
        assert session.status == "active"
        assert session.customer_id is None


class TestTenantConfig:
    def test_connector_config(self):
        cfg = ConnectorConfig(type="cosmosdb", connection="AccountEndpoint=...")
        assert cfg.type == "cosmosdb"
        assert cfg.database is None

    def test_tenant_config(self, tenant_config):
        assert tenant_config.tenant_id == "T-TEST"
        assert tenant_config.auto_confirm_threshold == 0.9
        assert "IOrderRepository" in tenant_config.connectors
