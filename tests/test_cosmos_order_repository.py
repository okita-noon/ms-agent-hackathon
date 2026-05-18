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
        "status": "未処理",
        "source": "LINE",
        "order_date": "2026-05-17",
        "delivery_date": "2026-05-18",
        "created_at": "2026-05-17T00:00:00",
        "updated_at": "2026-05-17T00:00:00",
    }


def _build_repo_with_container(mock_container: MagicMock):
    """Build a CosmosOrderRepository whose `_container` returns the given mock.

    Replaces the `_container` property on the instance via a property override
    on a one-off subclass so we don't touch the real class definition.
    """
    from src.connectors.adapters.cosmos_order_repository import CosmosOrderRepository

    config = ConnectorConfig(
        type="cosmosdb",
        connection="AccountEndpoint=https://test/;AccountKey=dGVzdA==;",
    )
    with patch("src.connectors.adapters.cosmos_order_repository.CosmosClient") as mock_client_cls:
        mock_client_cls.from_connection_string.return_value = MagicMock()
        repo = CosmosOrderRepository(config)

    class _Patched(type(repo)):
        @property
        def _container(self):
            return mock_container

    repo.__class__ = _Patched
    return repo


class TestFindByIdTenantIsolation:
    """find_by_id must enforce the caller's tenant_id against the stored doc."""

    @pytest.mark.asyncio
    async def test_returns_order_when_tenant_matches(self):
        mock_container = MagicMock()
        mock_container.read_item = AsyncMock(return_value=_make_order_doc("ORD-001", "T-001"))
        repo = _build_repo_with_container(mock_container)

        order = await repo.find_by_id("T-001", "ORD-001")

        assert order is not None
        assert order.tenant_id == "T-001"

    @pytest.mark.asyncio
    async def test_returns_none_when_tenant_mismatches(self):
        """IDOR guard: asking with T-002 must not return T-001's order."""
        mock_container = MagicMock()
        mock_container.read_item = AsyncMock(return_value=_make_order_doc("ORD-001", "T-001"))
        repo = _build_repo_with_container(mock_container)

        order = await repo.find_by_id("T-002", "ORD-001")

        assert order is None

    @pytest.mark.asyncio
    async def test_returns_none_when_doc_absent(self):
        mock_container = MagicMock()
        mock_container.read_item = AsyncMock(side_effect=Exception("not found"))
        repo = _build_repo_with_container(mock_container)

        order = await repo.find_by_id("T-001", "ORD-missing")

        assert order is None
