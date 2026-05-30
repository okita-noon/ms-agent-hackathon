"""数量異常severity判定の共通モジュール.

受注時（orchestrator）とダッシュボード（dashboard_agent）で同一閾値を
使うために純粋関数として切り出す。依存はモデル層のみ。
"""

from __future__ import annotations

from typing import Any, Literal

from src.models.intelligence import ProductStats

AnomalySeverity = Literal["high", "medium"]

# ── 定数 ──────────────────────────────────────────────────────────────────────
MIN_PROFILE_ORDERS: int = 3
FALLBACK_QTY_THRESHOLD: float = 100.0
Z_HIGH: float = 6.0
Z_MEDIUM: float = 3.0


def classify_quantity_anomaly(
    qty: float,
    unit: str,
    stats: ProductStats | None,
) -> dict[str, Any] | None:
    """数量が異常かどうかを判定し、異常なら severity を含む dict を返す。

    Returns:
        None          — 正常（異常なし）
        {severity, z_score, summary, typical_qty, typical_unit}
          severity: "high" | "medium"
          z_score:  float | None
          summary:  str（人向け説明）
          typical_qty: float | None
          typical_unit: str | None
    """
    if qty is None:
        return None

    if stats and stats.total_orders >= MIN_PROFILE_ORDERS:
        if stats.std_dev > 0:
            z_score = abs(qty - stats.avg_qty) / stats.std_dev
            if z_score <= Z_MEDIUM:
                return None
            severity: AnomalySeverity = "high" if z_score >= Z_HIGH else "medium"
            return {
                "severity": severity,
                "z_score": z_score,
                "summary": (
                    f"通常 {stats.avg_qty:g}{stats.typical_unit} 前後のところ "
                    f"{qty:g}{unit} で受注しています（Zスコア {z_score:.1f}）。"
                ),
                "typical_qty": stats.avg_qty,
                "typical_unit": stats.typical_unit,
            }
        if qty != stats.avg_qty:
            return {
                "severity": "medium",
                "z_score": None,
                "summary": (
                    f"通常 {stats.avg_qty:g}{stats.typical_unit} 固定のところ {qty:g}{unit} で受注しています。"
                ),
                "typical_qty": stats.avg_qty,
                "typical_unit": stats.typical_unit,
            }
        return None

    # プロファイル未蓄積フォールバック: 100個以上はmediumで警告
    if qty >= FALLBACK_QTY_THRESHOLD:
        return {
            "severity": "medium",
            "z_score": None,
            "summary": (
                f"過去パターンが未蓄積で {qty:g}{unit} の大口受注を検知しました。桁誤りの可能性を確認してください。"
            ),
            "typical_qty": None,
            "typical_unit": None,
        }
    return None
