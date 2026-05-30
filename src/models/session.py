from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class OrderSession(BaseModel):
    id: str
    tenant_id: str
    channel: str
    channel_user_id: str
    customer_id: str | None = None
    current_order_id: str | None = None
    current_order_snapshot: dict | None = None
    current_order_editable: bool = False
    agent_thread_id: str | None = None
    conversation_id: str | None = None
    last_external_message_id: str | None = None
    status: str = "active"
    pending_order_draft: dict | None = None
    pending_action_type: str | None = None
    shortage_review_order_id: str | None = None  # 在庫不足NEEDS_REVIEW受注のID（機会損失フォロー用）
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    last_message_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
