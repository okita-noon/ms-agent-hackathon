from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InboundAttachment(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    blob_url: str | None = None


class InboundMessage(BaseModel):
    tenant_id: str
    channel: Literal["line", "phone", "email"]
    channel_user_id: str
    customer_id: str | None = None
    customer_name: str | None = None
    subject: str | None = None
    text: str
    raw_text: str | None = None
    received_at: datetime
    external_message_id: str
    conversation_id: str | None = None
    reply_to_message_id: str | None = None
    attachments: list[InboundAttachment] = Field(default_factory=list)
