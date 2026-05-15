from __future__ import annotations

from typing import Annotated

from semantic_kernel.functions import kernel_function

from src.connectors.context import TenantContext


class AnomalyResult:
    def __init__(
        self,
        is_anomaly: bool,
        z_score: float = 0.0,
        avg_qty: float = 0.0,
        max_qty: float = 0.0,
        reason: str = "",
    ):
        self.is_anomaly = is_anomaly
        self.z_score = z_score
        self.avg_qty = avg_qty
        self.max_qty = max_qty
        self.reason = reason

    def to_dict(self) -> dict:
        return {
            "is_anomaly": self.is_anomaly,
            "z_score": self.z_score,
            "avg_qty": self.avg_qty,
            "max_qty": self.max_qty,
            "reason": self.reason,
        }


class ExceptionPlugin:
    def __init__(self, tenant_ctx: TenantContext):
        self._ctx = tenant_ctx

    @kernel_function(
        name="detect_quantity_anomaly",
        description="注文数量が顧客の過去パターンから著しく逸脱しているか検知する",
    )
    async def detect_quantity_anomaly(
        self,
        customer_id: Annotated[str, "顧客ID"],
        product_id: Annotated[str, "商品ID"],
        ordered_qty: Annotated[float, "注文数量"],
    ) -> dict:
        store = self._ctx.get_connector("IOrderIntelligenceStore")
        profile = await store.get_customer_profile(self._ctx.tenant_id, customer_id)
        if not profile:
            return AnomalyResult(is_anomaly=False, reason="プロファイルなし").to_dict()

        stats = profile.product_stats.get(product_id)
        if not stats or stats.total_orders < 3:
            return AnomalyResult(is_anomaly=False, reason="データ不足").to_dict()

        if stats.std_dev == 0:
            is_anomaly = ordered_qty != stats.avg_qty
            return AnomalyResult(
                is_anomaly=is_anomaly,
                avg_qty=stats.avg_qty,
                max_qty=stats.max_qty,
                reason=f"通常{stats.avg_qty}{stats.typical_unit}のところ{ordered_qty}{stats.typical_unit}"
                if is_anomaly
                else "",
            ).to_dict()

        z_score = abs(ordered_qty - stats.avg_qty) / stats.std_dev
        threshold = profile.anomaly_thresholds.get("qty_z_score", 3.0)
        is_anomaly = z_score > threshold

        return AnomalyResult(
            is_anomaly=is_anomaly,
            z_score=z_score,
            avg_qty=stats.avg_qty,
            max_qty=stats.max_qty,
            reason=(
                f"通常{stats.avg_qty}{stats.typical_unit}のところ{ordered_qty}{stats.typical_unit}"
                if is_anomaly
                else ""
            ),
        ).to_dict()

    @kernel_function(
        name="detect_unit_anomaly",
        description="注文の単位が顧客の通常使用単位と異なるか検知する",
    )
    async def detect_unit_anomaly(
        self,
        customer_id: Annotated[str, "顧客ID"],
        product_id: Annotated[str, "商品ID"],
        ordered_unit: Annotated[str, "注文で使用された単位"],
    ) -> dict:
        store = self._ctx.get_connector("IOrderIntelligenceStore")
        profile = await store.get_customer_profile(self._ctx.tenant_id, customer_id)
        if not profile:
            return {"is_anomaly": False, "reason": "プロファイルなし"}

        stats = profile.product_stats.get(product_id)
        if stats and stats.typical_unit != ordered_unit:
            return {
                "is_anomaly": True,
                "reason": f"通常は{stats.typical_unit}単位だが{ordered_unit}で注文",
                "typical_unit": stats.typical_unit,
            }
        return {"is_anomaly": False, "reason": ""}
