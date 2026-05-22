from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class OrderSession(BaseModel):
    id: str
    tenant_id: str
    channel: str
    channel_user_id: str
    customer_id: str | None = None
    agent_thread_id: str | None = None
    conversation_id: str | None = None
    last_external_message_id: str | None = None
    status: str = "active"
    pending_order_draft: dict | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    last_message_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
