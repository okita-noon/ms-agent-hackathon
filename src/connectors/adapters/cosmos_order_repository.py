from __future__ import annotations

import uuid
from datetime import date, datetime

from azure.cosmos.aio import CosmosClient, ContainerProxy

from src.models.order import Order, OrderStatus
from src.models.tenant import ConnectorConfig


class CosmosOrderRepository:
    def __init__(self, config: ConnectorConfig):
        self._client = CosmosClient.from_connection_string(config.connection)
        db_name = config.database or "orders"
        self._container_name = "order-documents"
        self._db = self._client.get_database_client(db_name)

    @property
    def _container(self) -> ContainerProxy:
        return self._db.get_container_client(self._container_name)

    async def save(self, order: Order) -> str:
        if not order.id:
            order.id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order.updated_at = datetime.utcnow()
        doc = order.model_dump(mode="json", by_alias=True)
        doc["id"] = order.id
        await self._container.upsert_item(doc)
        return order.id

    async def find_by_id(self, order_id: str) -> Order | None:
        try:
            doc = await self._container.read_item(order_id, partition_key=order_id)
            return Order.model_validate(doc)
        except Exception:
            return None

    async def list_by_date(self, tenant_id: str, target_date: date) -> list[Order]:
        query = (
            "SELECT * FROM c WHERE c.tenant_id = @tid AND c.delivery_date = @d "
            "ORDER BY c.customer_name"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@d", "value": target_date.isoformat()},
        ]
        items = self._container.query_items(query, parameters=params)
        return [Order.model_validate(doc) async for doc in items]

    async def list_by_customer(self, customer_id: str, limit: int = 50) -> list[Order]:
        query = (
            "SELECT TOP @limit * FROM c WHERE c.customer_id = @cid "
            "ORDER BY c.order_date DESC"
        )
        params = [
            {"name": "@cid", "value": customer_id},
            {"name": "@limit", "value": limit},
        ]
        items = self._container.query_items(query, parameters=params)
        return [Order.model_validate(doc) async for doc in items]

    async def update_status(self, order_id: str, status: OrderStatus) -> None:
        doc = await self._container.read_item(order_id, partition_key=order_id)
        doc["status"] = status.value
        doc["updated_at"] = datetime.utcnow().isoformat()
        await self._container.replace_item(order_id, doc)
