from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Any

from src.connectors.context import TenantContext
from src.models.intelligence import OrderPattern
from src.models.order import Order, OrderStatus
from src.utils.business_date import today_jst


class OrderMemoryService:
    """過去注文・学習パターンから注文ドラフトを復元するサービス。"""

    def __init__(self, ctx: TenantContext):
        self._ctx = ctx

    async def resolve_usual_order(self, customer_id: str, expression: str) -> dict[str, Any] | None:
        store = self._ctx.get_connector("IOrderIntelligenceStore")
        pattern: OrderPattern | None = await store.find_pattern_exact(
            self._ctx.tenant_id,
            customer_id,
            _normalize_expression(expression),
        )
        if not pattern:
            return None

        return await self._draft_from_pattern(customer_id, pattern)

    async def resolve_previous_order(self, customer_id: str) -> dict[str, Any] | None:
        repo = self._ctx.get_connector("IOrderRepository")
        orders = await repo.list_by_customer(customer_id, limit=10)
        # 「前と同じ」= 直前に確定した注文。配送日ではなく作成時刻で最新を選ぶ。
        candidates = [
            order for order in orders if order.status in {OrderStatus.ACCEPTED, OrderStatus.COMPLETED} and order.items
        ]
        if not candidates:
            return None
        order = sorted(candidates, key=_order_created_at_key, reverse=True)[0]
        return _draft_from_order(order)

    async def _draft_from_pattern(self, customer_id: str, pattern: OrderPattern) -> dict[str, Any]:
        product_master = self._ctx.get_connector("IProductMaster")
        items: list[dict[str, Any]] = []
        for resolved in pattern.resolved_items:
            product = await product_master.get_by_id(self._ctx.tenant_id, resolved.product_id)
            items.append(
                {
                    "product_id": resolved.product_id,
                    "product_name": resolved.product_name,
                    "quantity": resolved.qty,
                    "unit": resolved.unit,
                    "temperature_zone": product.temperature_zone.value if product else "常温",
                }
            )

        return {
            "customer_id": customer_id,
            "items": items,
            "delivery_date": today_jst(),
        }


def _draft_from_order(order: Order) -> dict[str, Any]:
    return {
        "customer_id": order.customer_id,
        "customer_name": order.customer_name,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit": item.unit,
                "temperature_zone": item.temperature_zone.value,
            }
            for item in order.items
        ],
        "delivery_date": today_jst(),
        "delivery_route": order.delivery_route,
        "delivery_carrier": order.delivery_carrier,
        "delivery_time_slot": order.delivery_time_slot,
    }


def _normalize_expression(expr: str) -> str:
    expr = unicodedata.normalize("NFKC", expr)
    expr = expr.strip().lower()
    return expr.replace(" ", "").replace("　", "")


def _order_created_at_key(order: Order) -> datetime:
    """作成時刻をソート用に正規化（naive は UTC とみなして aware に揃える）。"""
    dt = order.created_at
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
