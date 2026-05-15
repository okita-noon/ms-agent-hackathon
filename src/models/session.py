from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OrderSession(BaseModel):
    id: str
    tenant_id: str
    channel: str
    channel_user_id: str
    customer_id: str | None = None
    agent_thread_id: str | None = None
    status: str = "active"
    pending_order_draft: dict | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    last_message_at: datetime = Field(default_factory=datetime.utcnow)
