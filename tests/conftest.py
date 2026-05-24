from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Auth-related env vars must be set before importing src.auth.* (fail-closed defaults).
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-32bytes-aaaaaaaaaaaaaaaaaaa")
os.environ.setdefault("JWT_ISSUER", "orderai-api-test")
os.environ.setdefault("JWT_AUDIENCE", "orderai-dashboard-test")

# Mock aioodbc before any src imports (requires ODBC driver at import time)
if "aioodbc" not in sys.modules:
    sys.modules["aioodbc"] = MagicMock()

from src.connectors.context import TenantContext
from src.models.customer import Customer, CustomerDeliveryPreference
from src.models.intelligence import (
    CustomerOrderProfile,
    OrderPattern,
    ProductStats,
    ResolvedItem,
)
from src.models.product import Product, UnitType
from src.models.order import TemperatureZone
from src.models.tenant import ConnectorConfig, TenantConfig


@pytest.fixture
def tenant_config() -> TenantConfig:
    return TenantConfig(
        tenant_id="T-TEST",
        name="テスト環境",
        line_channel_id="test-channel",
        line_channel_secret="test-secret",
        line_channel_access_token="test-token",
        acs_connection_string="endpoint=https://test.communication.azure.com/;accesskey=dGVzdA==",
        acs_phone_number="+81501234567",
        auto_confirm_threshold=0.9,
        connectors={
            "IOrderRepository": ConnectorConfig(type="cosmosdb", connection="test"),
            "ISessionRepository": ConnectorConfig(type="cosmosdb", connection="test"),
            "IMessageHistoryRepository": ConnectorConfig(type="cosmosdb", connection="test"),
            "IOrderIntelligenceStore": ConnectorConfig(type="cosmosdb", connection="test"),
            "IProductMaster": ConnectorConfig(type="azure_sql", connection="test"),
            "ICustomerRepository": ConnectorConfig(type="azure_sql", connection="test"),
            "IInventoryService": ConnectorConfig(type="azure_sql", connection="test"),
        },
    )


@pytest.fixture
def mock_tenant_ctx(tenant_config) -> TenantContext:
    ctx = MagicMock(spec=TenantContext)
    ctx.tenant_id = tenant_config.tenant_id
    ctx.config = tenant_config
    ctx._connectors = {}

    def _get_connector(name):
        if name not in ctx._connectors:
            ctx._connectors[name] = AsyncMock()
            if name == "IMessageHistoryRepository":
                ctx._connectors[name].list_recent_messages.return_value = []
                ctx._connectors[name].create_message.side_effect = lambda message: message
        return ctx._connectors[name]

    ctx.get_connector = _get_connector
    return ctx


@pytest.fixture
def sample_customer() -> Customer:
    return Customer(
        id="C-001",
        tenant_id="T-TEST",
        name="ビストロ青葉",
        short_name="青葉",
        line_user_id="U1234567890",
        email="test@example.com",
        phone="03-1234-5678",
        delivery_preference=CustomerDeliveryPreference(),
        active=True,
    )


@pytest.fixture
def sample_product() -> Product:
    return Product(
        id="P-001",
        tenant_id="T-TEST",
        name="りんご",
        default_unit=UnitType.BOX,
        temperature_zone=TemperatureZone.CHILLED,
        active=True,
    )


@pytest.fixture
def sample_profile() -> CustomerOrderProfile:
    return CustomerOrderProfile(
        tenant_id="T-TEST",
        customer_id="C-001",
        product_stats={
            "P-001": ProductStats(
                avg_qty=15.0,
                std_dev=5.0,
                min_qty=5.0,
                max_qty=30.0,
                typical_unit="kg",
                total_orders=10,
            ),
        },
    )


@pytest.fixture
def sample_pattern() -> OrderPattern:
    return OrderPattern(
        tenant_id="T-TEST",
        customer_id="C-001",
        type="single",
        input_expression="ツナ缶100g",
        input_expression_normalized="ツナ缶100g",
        resolved_items=[
            ResolvedItem(product_id="P-010", product_name="ツナ缶", qty=1, unit="個"),
        ],
        confidence=0.7,
        occurrence_count=2,
        source="customer_confirmed",
    )
