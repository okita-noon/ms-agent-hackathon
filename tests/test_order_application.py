from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.services.order_application import OrderApplicationService


class _EventBroker:
    def __init__(self) -> None:
        self.publish = AsyncMock()


def _order(status: OrderStatus = OrderStatus.ACCEPTED) -> Order:
    return Order(
        uid="ORD-CURRENT",
        tenant_id="T-TEST",
        customer_id="C-001",
        customer_name="テスト社",
        order_date=date(2026, 5, 28),
        delivery_date=date(2026, 5, 29),
        source=OrderSource.LINE,
        status=status,
        items=[
            OrderItem(
                product_id="P-001",
                product_name="りんご",
                quantity=1,
                unit="箱",
                temperature_zone=TemperatureZone.CHILLED,
            )
        ],
    )


class TestOrderApplicationService:
    async def test_cancel_order_updates_status_and_publishes_event(self, mock_tenant_ctx):
        repo = mock_tenant_ctx.get_connector("IOrderRepository")
        repo.update_status = AsyncMock()
        broker = _EventBroker()

        result = await OrderApplicationService(mock_tenant_ctx, event_broker=broker).cancel_order(_order())

        assert result.cancelled is True
        assert result.needs_operator_review is False
        repo.update_status.assert_awaited_once_with("T-TEST", "ORD-CURRENT", OrderStatus.CANCELLED)
        broker.publish.assert_awaited_once()
        event, tenant_id, payload = broker.publish.call_args.args
        assert event == "order_updated"
        assert tenant_id == "T-TEST"
        assert payload["order_id"] == "ORD-CURRENT"
        assert payload["status"] == OrderStatus.CANCELLED.value

    async def test_cancel_order_requires_review_when_order_is_locked(self, mock_tenant_ctx):
        repo = mock_tenant_ctx.get_connector("IOrderRepository")
        repo.update_status = AsyncMock()
        broker = _EventBroker()

        result = await OrderApplicationService(mock_tenant_ctx, event_broker=broker).cancel_order(
            _order(status=OrderStatus.SHIPPING)
        )

        assert result.cancelled is False
        assert result.needs_operator_review is True
        repo.update_status.assert_not_awaited()
        broker.publish.assert_not_awaited()
