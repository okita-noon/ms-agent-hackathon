from __future__ import annotations

from datetime import date, datetime, timezone

from src.models.intelligence import OrderPattern, ResolvedItem
from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.services.order_memory import OrderMemoryService


class TestOrderMemoryService:
    async def test_resolve_usual_order_from_pattern(self, mock_tenant_ctx, sample_product):
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = OrderPattern(
            tenant_id="T-TEST",
            customer_id="C-001",
            input_expression="いつもの",
            input_expression_normalized="いつもの",
            resolved_items=[
                ResolvedItem(product_id="P-001", product_name="りんご", qty=2, unit="箱"),
            ],
            confidence=0.95,
        )
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.get_by_id.return_value = sample_product

        draft = await OrderMemoryService(mock_tenant_ctx).resolve_usual_order("C-001", "いつもの")

        assert draft is not None
        assert draft["customer_id"] == "C-001"
        assert draft["items"][0]["product_id"] == "P-001"
        assert draft["items"][0]["quantity"] == 2
        store.find_pattern_exact.assert_awaited_once_with("T-TEST", "C-001", "いつもの")

    async def test_resolve_previous_order_from_recent_accepted_order(self, mock_tenant_ctx):
        repo = mock_tenant_ctx.get_connector("IOrderRepository")
        repo.list_by_customer.return_value = [
            Order(
                uid="ORD-PREV",
                tenant_id="T-TEST",
                customer_id="C-001",
                customer_name="ビストロ青葉",
                order_date=date(2026, 5, 20),
                delivery_date=date(2026, 5, 21),
                source=OrderSource.LINE,
                status=OrderStatus.ACCEPTED,
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="りんご",
                        quantity=2,
                        unit="箱",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ],
            )
        ]

        draft = await OrderMemoryService(mock_tenant_ctx).resolve_previous_order("C-001")

        assert draft is not None
        assert draft["customer_id"] == "C-001"
        assert draft["items"][0]["product_name"] == "りんご"
        assert draft["items"][0]["quantity"] == 2

    async def test_resolve_previous_order_picks_latest_created_even_if_delivery_future(self, mock_tenant_ctx):
        # 「前と同じ」は配送日でなく作成時刻で直前の注文を選ぶ。
        # 古いが配送日が今日の注文(りんご200箱)より、直前に作った配送日が未来の注文(りんご3箱)を選ぶこと。
        def _order(uid, items_qty, order_date, delivery_date, created_at):
            return Order(
                uid=uid,
                tenant_id="T-TEST",
                customer_id="C-001",
                customer_name="ビストロ青葉",
                order_date=order_date,
                delivery_date=delivery_date,
                source=OrderSource.LINE,
                status=OrderStatus.ACCEPTED,
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="りんご",
                        quantity=items_qty,
                        unit="箱",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ],
                created_at=created_at,
            )

        repo = mock_tenant_ctx.get_connector("IOrderRepository")
        repo.list_by_customer.return_value = [
            # 配送日は今日だが作成は古い（旧データ・naive datetime）
            _order("ORD-OLD", 200, date(2026, 6, 1), date(2026, 6, 1), datetime(2026, 5, 31, 10, 0, 0)),
            # 直前に作成（配送日は未来）
            _order(
                "ORD-NEW", 3, date(2026, 6, 1), date(2026, 6, 3), datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
            ),
        ]

        draft = await OrderMemoryService(mock_tenant_ctx).resolve_previous_order("C-001")

        assert draft is not None
        # 直前に作成した3箱が選ばれること（200箱ではない）
        assert draft["items"][0]["quantity"] == 3
