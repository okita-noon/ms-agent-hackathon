from __future__ import annotations

from azure.cosmos.aio import CosmosClient, ContainerProxy

from src.models.message_history import MessageHistory
from src.models.tenant import ConnectorConfig


class CosmosMessageHistoryRepository:
    def __init__(self, config: ConnectorConfig):
        self._client = CosmosClient.from_connection_string(config.connection)
        db_name = config.database or "orders"
        self._db = self._client.get_database_client(db_name)

    @property
    def _container(self) -> ContainerProxy:
        return self._db.get_container_client("message-history")

    async def create_message(self, message: MessageHistory) -> MessageHistory:
        doc = message.model_dump(mode="json")
        await self._container.upsert_item(doc)
        return message

    async def list_recent_messages(
        self,
        tenant_id: str,
        channel: str,
        channel_user_id: str,
        limit: int = 20,
    ) -> list[MessageHistory]:
        query = (
            "SELECT * FROM c WHERE c.tenant_id = @tid "
            "AND c.channel = @ch AND c.channel_user_id = @uid "
            "ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@ch", "value": channel},
            {"name": "@uid", "value": channel_user_id},
            {"name": "@limit", "value": limit},
        ]
        items = self._container.query_items(query, parameters=params)
        messages: list[MessageHistory] = []
        async for doc in items:
            messages.append(MessageHistory.model_validate(doc))
        messages.reverse()
        return messages
