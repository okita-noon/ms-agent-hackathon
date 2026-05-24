from __future__ import annotations

import logging
import os

from src.connectors.context import TenantContext
from src.models.tenant import ConnectorConfig, TenantConfig

logger = logging.getLogger(__name__)

_TENANT_CACHE: dict[str, TenantConfig] = {}

# LINE channel ID → tenant ID mapping (for LINE webhook routing)
_LINE_CHANNEL_TENANT_MAP: dict[str, str] = {}

# ACS phone number → tenant ID mapping (for phone webhook routing)
_PHONE_TENANT_MAP: dict[str, str] = {}

# recipient email address → tenant ID mapping (for email webhook routing)
_EMAIL_TENANT_MAP: dict[str, str] = {}


def _get_tenant_config(tenant_id: str) -> TenantConfig:
    """Return TenantConfig for the given tenant_id.

    Both tenants share the same Azure infrastructure; data is partitioned
    by tenant_id within the SQL and Cosmos DB layers.
    """
    if tenant_id in _TENANT_CACHE:
        return _TENANT_CACHE[tenant_id]

    cosmos_conn = os.environ.get("COSMOS_CONNECTION_STRING", "")
    sql_conn = os.environ.get("SQL_CONNECTION_STRING", "")

    tenant_names: dict[str, str] = {
        "T-001": "AINOKハッカソン食品",
        "T-002": "鈴木青果",
    }

    if tenant_id not in tenant_names:
        logger.warning("Unknown tenant_id '%s', falling back to T-001", tenant_id)
        tenant_id = "T-001"

    # T-001 uses the shared LINE channel; T-002 shares the same infra for the demo.
    line_channel_id = os.environ.get("LINE_CHANNEL_ID") if tenant_id == "T-001" else None
    line_channel_secret = os.environ.get("LINE_CHANNEL_SECRET") if tenant_id == "T-001" else None
    line_channel_access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") if tenant_id == "T-001" else None

    # T-001 uses the shared ACS phone number for the demo.
    acs_conn = os.environ.get("ACS_CONNECTION_STRING") if tenant_id == "T-001" else None
    acs_phone = os.environ.get("ACS_PHONE_NUMBER") if tenant_id == "T-001" else None
    email_address = os.environ.get("GRAPH_MAILBOX_ADDRESS", "order@example.com") if tenant_id == "T-001" else None
    graph_client_id = os.environ.get("GRAPH_CLIENT_ID") if tenant_id == "T-001" else None
    graph_client_secret = os.environ.get("GRAPH_CLIENT_SECRET") if tenant_id == "T-001" else None
    graph_tenant_id = os.environ.get("GRAPH_TENANT_ID") if tenant_id == "T-001" else None
    graph_mailbox_user_id = os.environ.get("GRAPH_MAILBOX_USER_ID") if tenant_id == "T-001" else None

    config = TenantConfig(
        tenant_id=tenant_id,
        name=tenant_names[tenant_id],
        line_channel_id=line_channel_id,
        line_channel_secret=line_channel_secret,
        line_channel_access_token=line_channel_access_token,
        acs_connection_string=acs_conn,
        acs_phone_number=acs_phone,
        graph_client_id=graph_client_id,
        graph_client_secret=graph_client_secret,
        graph_tenant_id=graph_tenant_id,
        graph_mailbox_user_id=graph_mailbox_user_id,
        email_address=email_address,
        auto_confirm_threshold=0.9,
        connectors={
            "IOrderRepository": ConnectorConfig(type="cosmosdb", connection=cosmos_conn, database="orders"),
            "ISessionRepository": ConnectorConfig(type="cosmosdb", connection=cosmos_conn, database="orders"),
            "IMessageHistoryRepository": ConnectorConfig(type="cosmosdb", connection=cosmos_conn, database="orders"),
            "IOrderIntelligenceStore": ConnectorConfig(
                type="cosmosdb", connection=cosmos_conn, database="intelligence"
            ),
            "IProductMaster": ConnectorConfig(type="azure_sql", connection=sql_conn),
            "ICustomerRepository": ConnectorConfig(type="azure_sql", connection=sql_conn),
            "IInventoryService": ConnectorConfig(type="azure_sql", connection=sql_conn),
        },
    )

    _TENANT_CACHE[tenant_id] = config

    # Register LINE channel → tenant mapping for webhook routing
    if config.line_channel_id:
        _LINE_CHANNEL_TENANT_MAP[config.line_channel_id] = tenant_id

    # Register ACS phone number → tenant mapping for phone webhook routing
    if config.acs_phone_number:
        _PHONE_TENANT_MAP[config.acs_phone_number] = tenant_id

    # Register recipient email address → tenant mapping for email webhook routing
    if config.email_address:
        _EMAIL_TENANT_MAP[config.email_address.lower()] = tenant_id

    return config


# Keep legacy helper available for any callers that still use it.
def get_demo_tenant_config() -> TenantConfig:
    return _get_tenant_config("T-001")


def resolve_tenant_for_line(destination: str | None = None) -> TenantContext:
    """Resolve tenant from a LINE destination (channel ID).

    Falls back to T-001 when the channel ID is not mapped.
    """
    tenant_id = "T-001"
    if destination and destination in _LINE_CHANNEL_TENANT_MAP:
        tenant_id = _LINE_CHANNEL_TENANT_MAP[destination]
    config = _get_tenant_config(tenant_id)
    return TenantContext.from_config(config)


def resolve_tenant_for_phone(called_number: str) -> TenantContext:
    """Resolve tenant from an ACS phone number (the number the customer dialed).

    Falls back to T-001 when the phone number is not mapped.
    """
    tenant_id = "T-001"
    if called_number and called_number in _PHONE_TENANT_MAP:
        tenant_id = _PHONE_TENANT_MAP[called_number]
    config = _get_tenant_config(tenant_id)
    return TenantContext.from_config(config)


def resolve_tenant_for_email(recipient_address: str) -> TenantContext:
    """Resolve tenant from a recipient mailbox address.

    Falls back to T-001 when the mailbox address is not mapped.
    """
    tenant_id = "T-001"
    normalized = (recipient_address or "").strip().lower()
    if normalized and normalized in _EMAIL_TENANT_MAP:
        tenant_id = _EMAIL_TENANT_MAP[normalized]
    config = _get_tenant_config(tenant_id)
    return TenantContext.from_config(config)


def resolve_tenant_by_id(tenant_id: str) -> TenantContext:
    config = _get_tenant_config(tenant_id)
    return TenantContext.from_config(config)
