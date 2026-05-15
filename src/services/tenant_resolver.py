from __future__ import annotations

import logging
import os

from src.connectors.context import TenantContext
from src.models.tenant import ConnectorConfig, TenantConfig

logger = logging.getLogger(__name__)

_TENANT_CACHE: dict[str, TenantConfig] = {}


def get_demo_tenant_config() -> TenantConfig:
    cosmos_conn = os.environ.get("COSMOS_CONNECTION_STRING", "")
    sql_conn = os.environ.get("SQL_CONNECTION_STRING", "")

    return TenantConfig(
        tenant_id="T-001",
        name="デモ環境",
        line_channel_id=os.environ.get("LINE_CHANNEL_ID"),
        line_channel_secret=os.environ.get("LINE_CHANNEL_SECRET"),
        line_channel_access_token=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"),
        auto_confirm_threshold=0.9,
        connectors={
            "IOrderRepository": ConnectorConfig(
                type="cosmosdb", connection=cosmos_conn, database="orders"
            ),
            "ISessionRepository": ConnectorConfig(
                type="cosmosdb", connection=cosmos_conn, database="orders"
            ),
            "IOrderIntelligenceStore": ConnectorConfig(
                type="cosmosdb", connection=cosmos_conn, database="intelligence"
            ),
            "IProductMaster": ConnectorConfig(
                type="azure_sql", connection=sql_conn
            ),
            "ICustomerRepository": ConnectorConfig(
                type="azure_sql", connection=sql_conn
            ),
            "IInventoryService": ConnectorConfig(
                type="azure_sql", connection=sql_conn
            ),
        },
    )


def resolve_tenant_for_line(destination: str | None = None) -> TenantContext:
    config = get_demo_tenant_config()
    return TenantContext.from_config(config)


def resolve_tenant_by_id(tenant_id: str) -> TenantContext:
    config = get_demo_tenant_config()
    return TenantContext.from_config(config)
