from __future__ import annotations

from dataclasses import dataclass

from src.connectors.context import TenantContext
from src.models.order import Order, OrderStatus
from src.services.dashboard_events import DashboardEventBroker, dashboard_event_broker


EDITABLE_ORDER_STATUSES: frozenset[OrderStatus] = frozenset({OrderStatus.ACCEPTED, OrderStatus.NEEDS_REVIEW})


@dataclass(slots=True)
class CancelOrderResult:
    order: Order
    cancelled: bool
    needs_operator_review: bool


class OrderApplicationService:
    """注文状態変更の業務サービス。

    Agent/チャネル層は自然文理解と応答制御に集中し、注文ステータス更新や
    将来の在庫引当解除・変更履歴記録はこの層に集約する。
    """

    def __init__(
        self,
        ctx: TenantContext,
        *,
        event_broker: DashboardEventBroker = dashboard_event_broker,
    ):
        self._ctx = ctx
        self._event_broker = event_broker

    def is_order_editable(self, order: Order | None) -> bool:
        return bool(order and order.status in EDITABLE_ORDER_STATUSES)

    async def cancel_order(self, order: Order) -> CancelOrderResult:
        if not self.is_order_editable(order):
            return CancelOrderResult(order=order, cancelled=False, needs_operator_review=True)

        repo = self._ctx.get_connector("IOrderRepository")
        await repo.update_status(self._ctx.tenant_id, order.id, OrderStatus.CANCELLED)
        await self._event_broker.publish(
            "order_updated",
            self._ctx.tenant_id,
            {
                "order_id": order.id,
                "status": OrderStatus.CANCELLED.value,
                "reason": "status_updated",
                "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
                "order_date": order.order_date.isoformat(),
            },
        )
        return CancelOrderResult(order=order, cancelled=True, needs_operator_review=False)
