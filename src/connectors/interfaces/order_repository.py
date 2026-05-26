from __future__ import annotations

from datetime import date
from typing import Protocol

from src.models.order import Order, OrderStatus


class IOrderRepository(Protocol):
    async def save(self, order: Order) -> str: ...
    async def find_by_id(self, tenant_id: str, order_id: str) -> Order | None: ...
    async def list_orders(
        self,
        tenant_id: str,
        target_date: date | None = None,
        *,
        status: str | None = None,
        source: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
        date_field: str = "delivery_date",
    ) -> tuple[list[Order], int]: ...
    async def list_by_date(self, tenant_id: str, target_date: date) -> list[Order]: ...
    async def list_by_customer(self, customer_id: str, limit: int = 50) -> list[Order]: ...
    async def update_status(self, tenant_id: str, order_id: str, status: OrderStatus) -> None: ...
    async def update_memo(self, tenant_id: str, order_id: str, memo: str | None) -> Order: ...
