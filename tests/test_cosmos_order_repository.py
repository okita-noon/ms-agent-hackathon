from __future__ import annotations

from datetime import date
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


class _AsyncItems:
    def __init__(self, items: list[dict]):
        self._items = items

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for item in self._items:
            yield item


class TestListByDate:
    @pytest.mark.asyncio
    async def test_includes_needs_review_orders_by_order_date(self):
        """Inventory-shortage review orders must stay visible on the order list."""
        mock_container = MagicMock()
        review_doc = _make_order_doc("ORD-REVIEW", "T-001")
        review_doc["status"] = "要対応"
        review_doc["order_date"] = "2026-05-18"
        review_doc["delivery_date"] = "2026-05-19"
        mock_container.query_items.return_value = _AsyncItems([review_doc])
        repo = _build_repo_with_container(mock_container)

        orders = await repo.list_by_date("T-001", date(2026, 5, 18))

        assert [order.id for order in orders] == ["ORD-REVIEW"]
        args, kwargs = mock_container.query_items.call_args
        assert "c.delivery_date = @d OR (c.status = @needs_review AND c.order_date = @d)" in args[0]
        assert "c.source != @excluded_fax" in args[0]
        assert "c.source != @excluded_manual" in args[0]
        assert {"name": "@needs_review", "value": "要対応"} in kwargs["parameters"]
        assert {"name": "@excluded_fax", "value": "FAX"} in kwargs["parameters"]
        assert {"name": "@excluded_manual", "value": "手入力"} in kwargs["parameters"]


class TestListOrders:
    @pytest.mark.asyncio
    async def test_excludes_deferred_sources_from_dashboard_list(self):
        mock_container = MagicMock()
        mock_container.query_items.side_effect = [
            _AsyncItems([1]),
            _AsyncItems([_make_order_doc("ORD-001", "T-001")]),
        ]
        repo = _build_repo_with_container(mock_container)

        orders, total = await repo.list_orders("T-001", date(2026, 5, 18))

        assert total == 1
        assert [order.id for order in orders] == ["ORD-001"]
        count_query = mock_container.query_items.call_args_list[0].args[0]
        page_query = mock_container.query_items.call_args_list[1].args[0]
        page_params = mock_container.query_items.call_args_list[1].kwargs["parameters"]
        assert "c.source != @excluded_fax" in count_query
        assert "c.source != @excluded_manual" in page_query
        assert {"name": "@excluded_fax", "value": "FAX"} in page_params
        assert {"name": "@excluded_manual", "value": "手入力"} in page_params
