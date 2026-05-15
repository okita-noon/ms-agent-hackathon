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
    auto_confirm_threshold: float = 0.9
    connectors: dict[str, ConnectorConfig] = Field(default_factory=dict)
