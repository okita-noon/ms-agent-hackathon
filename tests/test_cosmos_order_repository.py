from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.tenant import ConnectorConfig


def _make_order_doc(order_id: str, tenant_id: str) -> dict:
    return {
        "id": order_id,
        "tenant_id": tenant_id,
        "customer_id": "C-001",
        "customer_name": "テスト顧客",
        "items": [],
        "status": "confirmed",
        "source": "line",
        "order_date": "2026-05-17",
        "delivery_date": "2026-05-18",
        "created_at": "2026-05-17T00:00:00",
        "updated_at": "2026-05-17T00:00:00",
    }


@pytest.fixture
def repo():
    """CosmosOrderRepository with the underlying Cosmos client patched out."""
    from src.connectors.adapters.cosmos_order_repository import CosmosOrderRepository

    config = ConnectorConfig(
        type="cosmosdb", connection="AccountEndpoint=https://test/;AccountKey=dGVzdA==;"
    )
    with patch(
        "src.connectors.adapters.cosmos_order_repository.CosmosClient"
    ) as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.from_connection_string.return_value = mock_client
        instance = CosmosOrderRepository(config)
    return instance


class TestFindByIdTenantIsolation:
    """find_by_id must enforce the caller's tenant_id against the stored doc."""

    @pytest.mark.asyncio
    async def test_returns_order_when_tenant_matches(self, repo):
        doc = _make_order_doc("ORD-001", "T-001")
        mock_container = MagicMock()
        mock_container.read_item = AsyncMock(return_value=doc)
        with patch.object(
            type(repo),
            "_container",
            new_callable=lambda: property(lambda self: mock_container),
        ):
            order = await repo.find_by_id("T-001", "ORD-001")
        assert order is not None
        assert order.tenant_id == "T-001"

    @pytest.mark.asyncio
    async def test_returns_none_when_tenant_mismatches(self, repo):
        """IDOR guard: asking with T-002 must not return T-001's order."""
        doc = _make_order_doc("ORD-001", "T-001")
        mock_container = MagicMock()
        mock_container.read_item = AsyncMock(return_value=doc)
        with patch.object(
            type(repo),
            "_container",
            new_callable=lambda: property(lambda self: mock_container),
        ):
            order = await repo.find_by_id("T-002", "ORD-001")
        assert order is None

    @pytest.mark.asyncio
    async def test_returns_none_when_doc_absent(self, repo):
        mock_container = MagicMock()
        mock_container.read_item = AsyncMock(side_effect=Exception("not found"))
        with patch.object(
            type(repo),
            "_container",
            new_callable=lambda: property(lambda self: mock_container),
        ):
            order = await repo.find_by_id("T-001", "ORD-missing")
        assert order is None
