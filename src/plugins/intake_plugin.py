from __future__ import annotations

import logging
import re
from typing import Annotated

from semantic_kernel.functions import kernel_function

from src.connectors.context import TenantContext
from src.models.customer import Customer
from src.models.intelligence import OrderPattern
from src.models.product import Product

logger = logging.getLogger(__name__)

# 数字の直後に来る表記ゆれ単位のマッピング（数字+単位 のパターンのみ対象）
_UNIT_ALIAS_MAP: dict[str, str] = {
    "コ": "個",
    "ケ": "個",
    "ヶ": "個",
    "ケース": "ケース",  # そのまま
    "キロ": "kg",
    "キログラム": "kg",
    "グラム": "g",
    "リットル": "L",
    "ミリ": "ml",
    "ミリリットル": "ml",
    "本": "本",  # そのまま（変換不要だが明示）
    "枚": "枚",
    "袋": "袋",
    "缶": "缶",
}

# 数字の直後に来る単位表記を正規化する正規表現
_UNIT_NORMALIZE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(" + "|".join(re.escape(k) for k in _UNIT_ALIAS_MAP) + r")\b")


def normalize_unit_in_text(text: str) -> str:
    """テキスト中の「数字+単位表記ゆれ」を正規化する。数字の直後の単位のみ対象。"""

    def _replace(m: re.Match) -> str:
        num = m.group(1)
        raw_unit = m.group(2)
        normalized = _UNIT_ALIAS_MAP.get(raw_unit, raw_unit)
        return f"{num}{normalized}"

    return _UNIT_NORMALIZE_PATTERN.sub(_replace, text)


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
        self._ctx.append_debug(
            f"[DB:Customer] lookup_customer: identifier={identifier!r} → found={customer is not None}, customer_id={customer.id if customer else 'なし'}, name={customer.name if customer else 'なし'}"
        )
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
        self._ctx.append_debug(
            f"[DB:Customer] lookup_customer_by_line_id: line_user_id={line_user_id!r} → found={customer is not None}, customer_id={customer.id if customer else 'なし'}, name={customer.name if customer else 'なし'}"
        )
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
        self._ctx.append_debug(
            f"[DB:Product] normalize_product: raw_name={raw_name!r} → found={product is not None}, product_id={product.id if product else 'なし'}, name={product.name if product else 'なし'}"
        )
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
            self._ctx.append_debug(
                f"[DB:Pattern] resolve_with_pattern: customer_id={customer_id!r}, expr={raw_expression!r} → found=False"
            )
            return None

        threshold = self._ctx.config.auto_confirm_threshold
        needs_confirmation = pattern.confidence < threshold
        self._ctx.append_debug(
            f"[DB:Pattern] resolve_with_pattern: customer_id={customer_id!r}, expr={raw_expression!r} → found=True, confidence={pattern.confidence}, needs_confirmation={needs_confirmation}"
        )
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
