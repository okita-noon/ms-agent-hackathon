from __future__ import annotations

from typing import Protocol

from src.models.customer import Customer


class ICustomerRepository(Protocol):
    async def find_by_identifier(
        self, tenant_id: str, identifier: str
    ) -> Customer | None: ...
    async def find_by_line_user_id(
        self, tenant_id: str, line_user_id: str
    ) -> Customer | None: ...
    async def get_by_id(self, tenant_id: str, customer_id: str) -> Customer | None: ...
    async def list_all(self, tenant_id: str) -> list[Customer]: ...
    async def update(
        self, tenant_id: str, customer_id: str, fields: dict
    ) -> Customer: ...
