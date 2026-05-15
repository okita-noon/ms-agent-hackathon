from __future__ import annotations

from typing import Protocol

from src.models.product import Product


class IProductMaster(Protocol):
    async def fuzzy_match(self, tenant_id: str, raw_name: str) -> Product | None: ...
    async def get_by_id(self, tenant_id: str, product_id: str) -> Product | None: ...
    async def list_all(self, tenant_id: str) -> list[Product]: ...
