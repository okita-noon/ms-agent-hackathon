from __future__ import annotations

from datetime import date

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
