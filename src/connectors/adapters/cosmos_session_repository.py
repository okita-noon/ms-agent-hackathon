from __future__ import annotations

from datetime import datetime

from azure.cosmos.aio import CosmosClient, ContainerProxy

from src.models.session import OrderSession
from src.models.tenant import ConnectorConfig


class CosmosSessionRepository:
    def __init__(self, config: ConnectorConfig):
        self._client = CosmosClient.from_connection_string(config.connection)
        db_name = config.database or "orders"
        self._db = self._client.get_database_client(db_name)

    @property
    def _container(self) -> ContainerProxy:
        return self._db.get_container_client("order-sessions")

    async def find_active_session(self, tenant_id: str, channel: str, channel_user_id: str) -> OrderSession | None:
        query = (
            "SELECT * FROM c WHERE c.tenant_id = @tid "
            "AND c.channel = @ch AND c.channel_user_id = @uid "
            "AND c.status IN ('active', 'awaiting_reply') "
            "ORDER BY c.created_at DESC OFFSET 0 LIMIT 1"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@ch", "value": channel},
            {"name": "@uid", "value": channel_user_id},
        ]
        items = self._container.query_items(query, parameters=params)
        async for doc in items:
            return OrderSession.model_validate(doc)
        return None

    async def find_by_conversation_id(self, tenant_id: str, conversation_id: str) -> OrderSession | None:
        query = (
            "SELECT * FROM c WHERE c.tenant_id = @tid "
            "AND c.conversation_id = @cid "
            "AND c.status IN ('active', 'awaiting_reply') "
            "ORDER BY c.created_at DESC OFFSET 0 LIMIT 1"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@cid", "value": conversation_id},
        ]
        items = self._container.query_items(query, parameters=params)
        async for doc in items:
            return OrderSession.model_validate(doc)
        return None

    async def create_session(self, session: OrderSession) -> OrderSession:
        doc = session.model_dump(mode="json")
        await self._container.create_item(doc)
        return session

    async def update_session(self, session: OrderSession) -> None:
        session.last_message_at = datetime.utcnow()
        doc = session.model_dump(mode="json")
        await self._container.upsert_item(doc)

    async def expire_session(self, session_id: str) -> None:
        try:
            doc = await self._container.read_item(session_id, partition_key=session_id)
            doc["status"] = "expired"
            await self._container.replace_item(session_id, doc)
        except Exception:
            pass
