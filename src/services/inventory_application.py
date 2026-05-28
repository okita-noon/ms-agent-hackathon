from __future__ import annotations

import logging
from typing import Any

from src.connectors.context import TenantContext

logger = logging.getLogger(__name__)


class InventoryApplicationService:
    """注文処理から使う在庫業務サービス。

    Connector はDB/API差し替えの境界に留め、注文ドラフト単位の在庫確認など
    チャネル共通の業務処理はこの層に寄せる。
    """

    def __init__(self, ctx: TenantContext):
        self._ctx = ctx

    async def check_draft_availability(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        inventory = self._ctx.get_connector("IInventoryService")
        checked_items: list[dict[str, Any]] = []
        for item in draft.get("items", []) or []:
            product_id = item.get("product_id")
            quantity = item.get("quantity")
            product_name = item.get("product_name") or product_id or "商品"
            unit = item.get("unit") or ""

            if not product_id or quantity is None:
                checked_items.append(
                    {
                        "product_id": product_id,
                        "product_name": product_name,
                        "required_qty": quantity,
                        "unit": unit,
                        "available_qty": None,
                        "is_sufficient": False,
                        "needs_confirmation": True,
                        "message": "商品または数量を確認できませんでした",
                    }
                )
                continue

            try:
                required_qty = float(quantity)
                status = await inventory.check(self._ctx.tenant_id, product_id, required_qty)
                status_product_name = status.product_name
                if isinstance(status_product_name, str) and status_product_name.strip() in {
                    "",
                    "不明",
                    "unknown",
                    "UNKNOWN",
                }:
                    status_product_name = None
                checked_items.append(
                    {
                        "product_id": product_id,
                        "product_name": status_product_name or product_name,
                        "required_qty": required_qty,
                        "unit": status.unit or unit,
                        "available_qty": status.available_qty,
                        "is_sufficient": status.is_sufficient,
                        "needs_confirmation": not status.is_sufficient,
                    }
                )
            except Exception:
                logger.exception("Inventory check failed for product %s", product_id)
                checked_items.append(
                    {
                        "product_id": product_id,
                        "product_name": product_name,
                        "required_qty": quantity,
                        "unit": unit,
                        "available_qty": None,
                        "is_sufficient": False,
                        "needs_confirmation": True,
                        "message": "在庫確認でエラーが発生しました",
                    }
                )
        return checked_items
