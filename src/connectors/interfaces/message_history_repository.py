from __future__ import annotations

from typing import Protocol

from src.models.message_history import MessageHistory


class IMessageHistoryRepository(Protocol):
    async def create_message(self, message: MessageHistory) -> MessageHistory: ...

    async def list_recent_messages(
        self,
        tenant_id: str,
        channel: str,
        channel_user_id: str,
        limit: int = 20,
    ) -> list[MessageHistory]: ...
