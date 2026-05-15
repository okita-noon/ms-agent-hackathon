from __future__ import annotations

import uuid

from azure.cosmos.aio import CosmosClient, ContainerProxy

from src.models.intelligence import CustomerOrderProfile, OrderPattern
from src.models.tenant import ConnectorConfig


class CosmosIntelligenceStore:
    def __init__(self, config: ConnectorConfig):
        self._client = CosmosClient.from_connection_string(config.connection)
        db_name = config.database or "intelligence"
        self._db = self._client.get_database_client(db_name)

    def _patterns(self) -> ContainerProxy:
        return self._db.get_container_client("order-patterns")

    def _profiles(self) -> ContainerProxy:
        return self._db.get_container_client("customer-profiles")

    async def find_pattern_exact(
        self, tenant_id: str, customer_id: str, normalized_expression: str
    ) -> OrderPattern | None:
        query = (
            "SELECT * FROM c WHERE c.tenant_id = @tid "
            "AND c.customer_id = @cid "
            "AND c.input_expression_normalized = @expr"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@cid", "value": customer_id},
            {"name": "@expr", "value": normalized_expression},
        ]
        items = self._patterns().query_items(query, parameters=params)
        async for doc in items:
            return OrderPattern.model_validate(doc)
        return None

    async def find_pattern_by_embedding(
        self,
        tenant_id: str,
        customer_id: str,
        embedding: list[float],
        similarity_threshold: float = 0.85,
    ) -> OrderPattern | None:
        exact = await self.find_pattern_exact(tenant_id, customer_id, "")
        if exact:
            return exact

        query = (
            "SELECT * FROM c WHERE c.tenant_id = @tid AND c.customer_id = @cid"
        )
        params = [
            {"name": "@tid", "value": tenant_id},
            {"name": "@cid", "value": customer_id},
        ]
        best: OrderPattern | None = None
        best_sim = 0.0
        items = self._patterns().query_items(query, parameters=params)
        async for doc in items:
            pattern = OrderPattern.model_validate(doc)
            if pattern.input_embedding:
                sim = _cosine_similarity(embedding, pattern.input_embedding)
                if sim > best_sim and sim >= similarity_threshold:
                    best_sim = sim
                    best = pattern
        return best

    async def create_pattern(self, pattern: OrderPattern) -> OrderPattern:
        if not pattern.id:
            pattern.id = f"pat-{uuid.uuid4().hex[:12]}"
        doc = pattern.model_dump(mode="json")
        await self._patterns().create_item(doc)
        return pattern

    async def update_pattern(self, pattern: OrderPattern) -> OrderPattern:
        doc = pattern.model_dump(mode="json")
        await self._patterns().upsert_item(doc)
        return pattern

    async def get_customer_profile(
        self, tenant_id: str, customer_id: str
    ) -> CustomerOrderProfile | None:
        profile_id = f"prof-{customer_id}"
        try:
            doc = await self._profiles().read_item(profile_id, partition_key=customer_id)
            return CustomerOrderProfile.model_validate(doc)
        except Exception:
            return None

    async def upsert_profile(self, profile: CustomerOrderProfile) -> CustomerOrderProfile:
        if not profile.id:
            profile.id = f"prof-{profile.customer_id}"
        doc = profile.model_dump(mode="json")
        await self._profiles().upsert_item(doc)
        return profile


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
