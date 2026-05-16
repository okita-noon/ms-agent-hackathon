from __future__ import annotations

import logging
import unicodedata
from datetime import datetime

from src.connectors.context import TenantContext
from src.models.intelligence import (
    CustomerOrderProfile,
    OrderPattern,
    ProductStats,
    ResolvedItem,
)

logger = logging.getLogger(__name__)


class LearningService:
    def __init__(self, tenant_ctx: TenantContext):
        self._ctx = tenant_ctx

    async def record_pattern(
        self,
        customer_id: str,
        input_expression: str,
        resolved_items: list[ResolvedItem],
        source: str = "customer_confirmed",
    ) -> OrderPattern:
        store = self._ctx.get_connector("IOrderIntelligenceStore")
        normalized = _normalize_expression(input_expression)

        existing = await store.find_pattern_exact(self._ctx.tenant_id, customer_id, normalized)

        if existing and _same_resolution(existing.resolved_items, resolved_items):
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.occurrence_count += 1
            existing.last_confirmed_at = datetime.utcnow()
            return await store.update_pattern(existing)

        pattern_type = "template" if len(resolved_items) > 1 else "single"
        pattern = OrderPattern(
            tenant_id=self._ctx.tenant_id,
            customer_id=customer_id,
            type=pattern_type,
            input_expression=input_expression,
            input_expression_normalized=normalized,
            resolved_items=resolved_items,
            confidence=0.5 if source == "agent_inferred" else 0.7,
            occurrence_count=1,
            source=source,
        )
        return await store.create_pattern(pattern)

    async def update_customer_profile(
        self,
        customer_id: str,
        product_id: str,
        quantity: float,
        unit: str,
    ) -> CustomerOrderProfile:
        store = self._ctx.get_connector("IOrderIntelligenceStore")
        profile = await store.get_customer_profile(self._ctx.tenant_id, customer_id)
        if not profile:
            profile = CustomerOrderProfile(
                tenant_id=self._ctx.tenant_id,
                customer_id=customer_id,
            )

        stats = profile.product_stats.get(product_id, ProductStats())
        n = stats.total_orders

        if n == 0:
            stats.avg_qty = quantity
            stats.std_dev = quantity * 0.3
            stats.min_qty = quantity
            stats.max_qty = quantity
        else:
            new_avg = (stats.avg_qty * n + quantity) / (n + 1)
            if n >= 1:
                variance = (stats.std_dev**2 * n + (quantity - new_avg) * (quantity - stats.avg_qty)) / (n + 1)
                stats.std_dev = max(variance, 0) ** 0.5
            stats.avg_qty = new_avg
            stats.min_qty = min(stats.min_qty, quantity)
            stats.max_qty = max(stats.max_qty, quantity)

        stats.typical_unit = unit
        stats.total_orders = n + 1
        stats.last_ordered_at = datetime.utcnow().strftime("%Y-%m-%d")

        profile.product_stats[product_id] = stats
        return await store.upsert_profile(profile)


def _normalize_expression(expr: str) -> str:
    expr = unicodedata.normalize("NFKC", expr)
    expr = expr.strip().lower()
    expr = expr.replace(" ", "").replace("　", "")
    return expr


def _same_resolution(a: list[ResolvedItem], b: list[ResolvedItem]) -> bool:
    return sorted(i.product_id for i in a) == sorted(i.product_id for i in b)
