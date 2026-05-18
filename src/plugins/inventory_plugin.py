from __future__ import annotations

from typing import Annotated

from semantic_kernel.functions import kernel_function

from src.connectors.context import TenantContext


class InventoryPlugin:
    def __init__(self, tenant_ctx: TenantContext):
        self._ctx = tenant_ctx

    @kernel_function(
        name="check_inventory",
        description="指定された商品の在庫数量を確認する",
    )
    async def check_inventory(
        self,
        product_id: Annotated[str, "商品ID"],
        required_qty: Annotated[float, "必要数量"],
    ) -> dict:
        svc = self._ctx.get_connector("IInventoryService")
        result = await svc.check(self._ctx.tenant_id, product_id, required_qty)
        return result.model_dump()

    @kernel_function(
        name="find_alternatives",
        description="在庫不足時に同カテゴリの代替品を提案する",
    )
    async def find_alternatives(
        self,
        product_id: Annotated[str, "在庫不足の商品ID"],
        required_qty: Annotated[float, "必要数量"],
    ) -> list[dict]:
        svc = self._ctx.get_connector("IInventoryService")
        results = await svc.find_alternatives(
            self._ctx.tenant_id, product_id, required_qty
        )
        return [r.model_dump() for r in results]

    @kernel_function(
        name="reserve_inventory",
        description="在庫を確保（引き当て）する",
    )
    async def reserve_inventory(
        self,
        product_id: Annotated[str, "商品ID"],
        qty: Annotated[float, "確保数量"],
    ) -> dict:
        svc = self._ctx.get_connector("IInventoryService")
        result = await svc.reserve(self._ctx.tenant_id, product_id, qty)
        return result.model_dump()
