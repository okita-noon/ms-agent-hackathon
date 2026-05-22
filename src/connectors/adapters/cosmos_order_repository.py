from __future__ import annotations

import uuid
from datetime import date, datetime

from azure.core import MatchConditions
from azure.cosmos.aio import CosmosClient, ContainerProxy
from azure.cosmos.exceptions import CosmosAccessConditionFailedError

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

    async def find_by_id(self, tenant_id: str, order_id: str) -> Order | None:
        try:
            doc = await self._container.read_item(order_id, partition_key=tenant_id)
        except Exception:
            return None
        if doc.get("tenant_id") != tenant_id:
            return None
        return Order.model_validate(doc)

    async def list_by_date(self, tenant_id: str, target_date: date) -> list[Order]:
        query = (
            "SELECT * FROM c "
            "WHERE c.tenant_id = @tid "
            "AND (c.delivery_date = @d OR (c.status = @needs_review AND c.order_date = @d)) "
            "ORDER BY c.customer_name"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@d", "value": target_date.isoformat()},
            {"name": "@needs_review", "value": OrderStatus.NEEDS_REVIEW.value},
        ]
        items = self._container.query_items(query, parameters=params)
        return [Order.model_validate(doc) async for doc in items]

    async def list_orders(
        self,
        tenant_id: str,
        target_date: date,
        *,
        status: str | None = None,
        source: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        where = ["c.tenant_id = @tid", "c.delivery_date = @d"]
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@d", "value": target_date.isoformat()},
        ]

        if status:
            where.append("c.status = @status")
            params.append({"name": "@status", "value": status})
        if source:
            where.append("c.source = @source")
            params.append({"name": "@source", "value": source})

        normalized_q = q.strip().lower() if q else ""
        if normalized_q:
            where.append(
                "("
                "CONTAINS(LOWER(c.customer_name), @q) "
                "OR CONTAINS(LOWER(c.customer_id), @q) "
                "OR EXISTS(SELECT VALUE i FROM i IN c.items WHERE CONTAINS(LOWER(i.product_name), @q))"
                ")"
            )
            params.append({"name": "@q", "value": normalized_q})

        where_clause = " AND ".join(where)
        count_query = f"SELECT VALUE COUNT(1) FROM c WHERE {where_clause}"
        count_items = self._container.query_items(count_query, parameters=params)
        total = 0
        async for count in count_items:
            total = int(count)
            break

        page_params = [
            *params,
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": limit},
        ]
        page_query = f"SELECT * FROM c WHERE {where_clause} ORDER BY c.customer_name OFFSET @offset LIMIT @limit"
        items = self._container.query_items(page_query, parameters=page_params)
        orders = [Order.model_validate(doc) async for doc in items]
        return orders, total

    async def list_by_customer(self, customer_id: str, limit: int = 50) -> list[Order]:
        query = "SELECT TOP @limit * FROM c WHERE c.customer_id = @cid ORDER BY c.order_date DESC"
        params = [
            {"name": "@cid", "value": customer_id},
            {"name": "@limit", "value": limit},
        ]
        items = self._container.query_items(query, parameters=params)
        return [Order.model_validate(doc) async for doc in items]

    async def update_status(self, tenant_id: str, order_id: str, status: OrderStatus) -> None:
        for attempt in range(3):
            doc = await self._container.read_item(order_id, partition_key=tenant_id)
            etag = doc.get("_etag")
            doc["status"] = status.value
            doc["updated_at"] = datetime.utcnow().isoformat()
            try:
                await self._container.replace_item(
                    order_id,
                    doc,
                    match_condition=MatchConditions.IfNotModified,
                    etag=etag,
                )
                return
            except CosmosAccessConditionFailedError:
                if attempt == 2:
                    raise
