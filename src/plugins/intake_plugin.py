from __future__ import annotations

import logging
from typing import Annotated

from semantic_kernel.functions import kernel_function

from src.connectors.context import TenantContext
from src.models.customer import Customer
from src.models.intelligence import OrderPattern
from src.models.product import Product

logger = logging.getLogger(__name__)


class PatternMatch:
    def __init__(
        self,
        pattern: OrderPattern,
        needs_confirmation: bool,
    ):
        self.pattern = pattern
        self.resolved_items = pattern.resolved_items
        self.confidence = pattern.confidence
        self.needs_confirmation = needs_confirmation


class IntakePlugin:
    def __init__(self, tenant_ctx: TenantContext):
        self._ctx = tenant_ctx

    @kernel_function(
        name="lookup_customer",
        description="顧客名/LINE ID/電話番号から顧客を特定する",
    )
    async def lookup_customer(
        self,
        identifier: Annotated[str, "LINE User ID、電話番号、またはメールアドレス"],
    ) -> dict:
        repo = self._ctx.get_connector("ICustomerRepository")
        customer: Customer | None = await repo.find_by_identifier(self._ctx.tenant_id, identifier)
        if not customer:
            return {"found": False, "identifier": identifier}
        return {"found": True, **customer.model_dump()}

    @kernel_function(
        name="lookup_customer_by_line_id",
        description="LINE User IDから顧客を特定する",
    )
    async def lookup_customer_by_line_id(
        self,
        line_user_id: Annotated[str, "LINE User ID"],
    ) -> dict:
        repo = self._ctx.get_connector("ICustomerRepository")
        customer: Customer | None = await repo.find_by_line_user_id(self._ctx.tenant_id, line_user_id)
        if not customer:
            return {"found": False, "line_user_id": line_user_id}
        return {"found": True, **customer.model_dump()}

    @kernel_function(
        name="normalize_product",
        description="商品名の表記ゆれを正規化する。あいまい検索で最も近い商品を返す",
    )
    async def normalize_product(
        self,
        raw_name: Annotated[str, "顧客が入力した商品名（表記ゆれ含む）"],
    ) -> dict:
        master = self._ctx.get_connector("IProductMaster")
        product: Product | None = await master.fuzzy_match(self._ctx.tenant_id, raw_name)
        if not product:
            return {"found": False, "raw_name": raw_name}
        return {"found": True, **product.model_dump()}

    @kernel_function(
        name="resolve_with_pattern",
        description=(
            "過去の発注パターンに基づいて曖昧な表現を解釈する。"
            "パターンが見つかれば解釈結果とconfidenceを返す。初回ならnullを返す。"
        ),
    )
    async def resolve_with_pattern(
        self,
        customer_id: Annotated[str, "顧客ID"],
        raw_expression: Annotated[str, "顧客の生の注文表現（例: ツナ缶100g）"],
    ) -> dict | None:
        store = self._ctx.get_connector("IOrderIntelligenceStore")
        normalized = _normalize_expression(raw_expression)

        pattern = await store.find_pattern_exact(self._ctx.tenant_id, customer_id, normalized)
        if not pattern:
            return None

        threshold = self._ctx.config.auto_confirm_threshold
        needs_confirmation = pattern.confidence < threshold
        return {
            "resolved_items": [item.model_dump() for item in pattern.resolved_items],
            "confidence": pattern.confidence,
            "needs_confirmation": needs_confirmation,
            "pattern_id": pattern.id,
        }


def _normalize_expression(expr: str) -> str:
    import unicodedata

    expr = unicodedata.normalize("NFKC", expr)
    expr = expr.strip().lower()
    expr = expr.replace(" ", "").replace("　", "")
    return expr
