from __future__ import annotations

from pydantic import BaseModel, Field


class ConnectorConfig(BaseModel):
    type: str
    connection: str | None = None
    endpoint: str | None = None
    database: str | None = None
    index: str | None = None
    extra: dict = Field(default_factory=dict)


class TenantConfig(BaseModel):
    tenant_id: str
    name: str
    line_channel_id: str | None = None
    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    acs_connection_string: str | None = None
    acs_phone_number: str | None = None
    graph_client_id: str | None = None
    graph_client_secret: str | None = None
    graph_tenant_id: str | None = None
    graph_mailbox_user_id: str | None = None
    email_address: str | None = None
    auto_confirm_threshold: float = 0.9
    connectors: dict[str, ConnectorConfig] = Field(default_factory=dict)
