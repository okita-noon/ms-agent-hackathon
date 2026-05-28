from __future__ import annotations

from src.connectors.interfaces.inventory_service import InventoryStatus
from src.services.inventory_application import InventoryApplicationService


class TestInventoryApplicationService:
    async def test_check_draft_availability_checks_each_item(self, mock_tenant_ctx):
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="りんご",
            available_qty=5,
            unit="箱",
            is_sufficient=True,
        )
        draft = {
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 2,
                    "unit": "箱",
                }
            ]
        }

        result = await InventoryApplicationService(mock_tenant_ctx).check_draft_availability(draft)

        inventory.check.assert_awaited_once_with("T-TEST", "P-001", 2.0)
        assert result == [
            {
                "product_id": "P-001",
                "product_name": "りんご",
                "required_qty": 2.0,
                "unit": "箱",
                "available_qty": 5,
                "is_sufficient": True,
                "needs_confirmation": False,
            }
        ]

    async def test_check_draft_availability_marks_missing_quantity_for_confirmation(self, mock_tenant_ctx):
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        draft = {
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "unit": "箱",
                }
            ]
        }

        result = await InventoryApplicationService(mock_tenant_ctx).check_draft_availability(draft)

        inventory.check.assert_not_called()
        assert result[0]["is_sufficient"] is False
        assert result[0]["needs_confirmation"] is True
        assert result[0]["message"] == "商品または数量を確認できませんでした"
