from __future__ import annotations

from typing import Protocol

from src.models.intelligence import CustomerOrderProfile, OrderPattern


class IOrderIntelligenceStore(Protocol):
    async def find_pattern_by_embedding(
        self,
        tenant_id: str,
        customer_id: str,
        embedding: list[float],
        similarity_threshold: float = 0.85,
    ) -> OrderPattern | None: ...

    async def find_pattern_exact(
        self, tenant_id: str, customer_id: str, normalized_expression: str
    ) -> OrderPattern | None: ...

    async def create_pattern(self, pattern: OrderPattern) -> OrderPattern: ...
    async def update_pattern(self, pattern: OrderPattern) -> OrderPattern: ...

    async def get_customer_profile(self, tenant_id: str, customer_id: str) -> CustomerOrderProfile | None: ...
    async def upsert_profile(self, profile: CustomerOrderProfile) -> CustomerOrderProfile: ...
