from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "system"]


class MessageHistory(BaseModel):
    id: str
    tenant_id: str
    session_id: str
    channel: str
    channel_user_id: str
    role: MessageRole
    text: str
    message_id: str | None = None
    webhook_event_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
