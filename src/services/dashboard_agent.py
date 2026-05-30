"""Dashboard Agent サービス.

`docs/multi-agent-design.md` の Exception Agent / Learning Service の知見を
ダッシュボード側でも扱えるよう薄くラップしたサービス。

- 配送日単位で注文を走査し、担当者の判断が必要な「Exception Case」を集約
- CustomerOrderProfile（Z-score）と IInventoryService を使った客観的な検知
- 個々の Exception に対する Resolution Agent のプレビュー（顧客向け文面・推奨アクション）

LLM 推論は行わず、Connector 経由のデータと既存のドメインモデルで決定論的に
組み立てる。Communication への実送信は本サービスでは行わず、ダッシュボード側で
担当者が承認したうえで Orchestrator/Communication Agent に委譲する想定。
"""

from __future__ import annotations

import os
from datetime import date
from hashlib import sha1
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.connectors.context import TenantContext
from src.models.intelligence import CustomerOrderProfile, ProductStats
from src.models.order import Order, OrderItem, OrderStatus
from src.services.anomaly_rules import classify_quantity_anomaly

ExceptionCaseType = Literal[
    "quantity_anomaly",
    "unit_anomaly",
    "inventory_shortage",
    "needs_review",
]
ExceptionSeverity = Literal["high", "medium", "low"]

TRUTHY = {"1", "true", "yes", "on", "enabled"}
SEVERITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED})


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUTHY


class AgentFeatures(BaseModel):
    dashboard_agent: bool
    exception_triage: bool
    resolution_agent: bool
    resolution_execute: bool
    demo_mode: bool


class Evidence(BaseModel):
    label: str
    value: str


class ExceptionCase(BaseModel):
    id: str
    order_id: str
    customer_id: str
    customer_name: str
    type: ExceptionCaseType
    severity: ExceptionSeverity
    title: str
    summary: str
    suggested_action: str
    evidence: list[Evidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolutionPreview(BaseModel):
    exception_id: str
    title: str
    summary: str
    confidence: float = 0.0
    recommended_actions: list[str] = Field(default_factory=list)
    customer_message: str = ""
    requires_approval: bool = True


class DashboardAgentService:
    """ダッシュボード向け Exception / Resolution エージェント本体."""

    def __init__(self, tenant_ctx: TenantContext) -> None:
        self._ctx = tenant_ctx

    @staticmethod
    def features() -> AgentFeatures:
        dashboard = _env_flag("DASHBOARD_AGENT_ENABLED")
        return AgentFeatures(
            dashboard_agent=dashboard,
            exception_triage=dashboard and _env_flag("DASHBOARD_EXCEPTION_TRIAGE_ENABLED", default=True),
            resolution_agent=dashboard and _env_flag("DASHBOARD_RESOLUTION_AGENT_ENABLED", default=True),
            resolution_execute=dashboard and _env_flag("DASHBOARD_RESOLUTION_EXECUTE_ENABLED"),
            demo_mode=_env_flag("DASHBOARD_AGENT_DEMO_MODE"),
        )

    async def list_exception_cases(self, tenant_id: str, delivery_date: date) -> list[ExceptionCase]:
        repo = self._ctx.get_connector("IOrderRepository")
        orders: list[Order] = await repo.list_by_date(tenant_id, delivery_date)
        return await self._classify_orders(tenant_id, orders)

    async def list_exception_cases_for_order_list(
        self,
        tenant_id: str,
        target_date: date | None = None,
        *,
        status: str | None = None,
        source: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
        date_field: str = "delivery_date",
    ) -> list[ExceptionCase]:
        repo = self._ctx.get_connector("IOrderRepository")
        orders, _total = await repo.list_orders(
            tenant_id,
            target_date,
            status=status,
            source=source,
            q=q,
            limit=limit,
            offset=offset,
            date_field=date_field,
        )
        return await self._classify_orders(tenant_id, orders)

    async def _classify_orders(self, tenant_id: str, orders: list[Order]) -> list[ExceptionCase]:
        if not orders:
            return []

        store = self._ctx.get_connector("IOrderIntelligenceStore")
        inventory = self._ctx.get_connector("IInventoryService")

        profiles: dict[str, CustomerOrderProfile | None] = {}
        cases: list[ExceptionCase] = []
        for order in orders:
            # 完了・キャンセル済みは担当者の対応が不要なので triage 対象外
            if order.status in TERMINAL_STATUSES:
                continue
            profile = profiles.get(order.customer_id)
            if profile is None and order.customer_id not in profiles:
                profile = await _safe_get_profile(store, tenant_id, order.customer_id)
                profiles[order.customer_id] = profile

            specific_cases: list[ExceptionCase] = []
            specific_cases.extend(_classify_items(order, profile))
            specific_cases.extend(await _classify_inventory(order, tenant_id, inventory))

            status_cases = _classify_status(order)
            if status_cases:
                # needs_review は medium がデフォルト。specific_cases に high があれば high に昇格
                has_high = any(c.severity == "high" for c in specific_cases)
                for sc in status_cases:
                    if sc.type == "needs_review" and has_high:
                        sc = sc.model_copy(update={"severity": "high"})
                    cases.append(sc)
            cases.extend(specific_cases)

        cases.sort(key=lambda c: (SEVERITY_RANK.get(c.severity, 99), c.order_id))
        return cases

    async def preview_resolution(self, case: ExceptionCase) -> ResolutionPreview:
        if case.type == "quantity_anomaly":
            return _preview_quantity_anomaly(case)
        if case.type == "unit_anomaly":
            return _preview_unit_anomaly(case)
        if case.type == "inventory_shortage":
            return await self._preview_inventory_shortage(case)
        return _preview_needs_review(case)

    async def _preview_inventory_shortage(self, case: ExceptionCase) -> ResolutionPreview:
        product_id = str(case.metadata.get("product_id") or "")
        required = _coerce_float(case.metadata.get("required_qty"))
        alternatives_meta: list[dict[str, Any]] = []
        if product_id and required is not None:
            inventory = self._ctx.get_connector("IInventoryService")
            try:
                alts = await inventory.find_alternatives(self._ctx.tenant_id, product_id, required)
            except Exception:  # noqa: BLE001 -- 検索失敗時は空のプレビューに留める
                alts = []
            alternatives_meta = [
                {
                    "product_id": alt.product_id,
                    "product_name": alt.product_name,
                    "available_qty": alt.available_qty,
                    "unit": alt.unit,
                }
                for alt in alts[:3]
            ]
        return _preview_inventory_shortage_body(case, alternatives_meta)


_SHORTAGE_FOLLOWUP_MARKER = "在庫不足により数量変更あり"


def _classify_status(order: Order) -> list[ExceptionCase]:
    cases = []
    if order.status == OrderStatus.NEEDS_REVIEW:
        cases.append(
            _build_case(
                order=order,
                case_type="needs_review",
                severity="medium",
                title="担当者確認が必要な受注",
                summary="AIが自動処理できず「要対応」となっています。",
                suggested_action="注文内容と会話履歴を確認し、必要なら顧客へ問い合わせてください。",
                evidence=[Evidence(label="ステータス", value=order.status.value)],
            )
        )
    # 在庫不足による数量変更受注 → 機会損失フォロー用に high で通知
    if order.remarks and _SHORTAGE_FOLLOWUP_MARKER in order.remarks:
        cases.append(
            _build_case(
                order=order,
                case_type="needs_review",
                severity="high",
                title="在庫不足による数量変更あり（フォロー推奨）",
                summary="在庫不足のため顧客が希望数量を減らして注文しました。在庫手配が可能か確認し、追加対応を検討してください。",
                suggested_action="会話履歴で元の希望数量を確認し、仕入れ状況次第で顧客へ追加案内を行ってください。",
                evidence=[Evidence(label="備考", value=order.remarks)],
            )
        )
    return cases


def _classify_items(order: Order, profile: CustomerOrderProfile | None) -> list[ExceptionCase]:
    cases: list[ExceptionCase] = []
    for index, item in enumerate(order.items):
        if item.quantity is None:
            continue
        stats = _stats_for(profile, item.product_id)
        anomaly = _quantity_anomaly(item, stats)
        if anomaly is not None:
            cases.append(
                _build_case(
                    order=order,
                    case_type="quantity_anomaly",
                    severity=anomaly["severity"],
                    title=f"{item.product_name}の数量異常",
                    summary=anomaly["summary"],
                    suggested_action="桁誤りの可能性を確認し、必要なら修正案を顧客に確認してください。",
                    evidence=anomaly["evidence"],
                    metadata={
                        "item_index": index,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "ordered_qty": item.quantity,
                        "unit": item.unit,
                        "typical_qty": stats.avg_qty if stats else None,
                        "typical_unit": stats.typical_unit if stats else item.unit,
                        "z_score": anomaly.get("z_score"),
                    },
                )
            )
        if stats and stats.typical_unit and stats.typical_unit != item.unit:
            cases.append(
                _build_case(
                    order=order,
                    case_type="unit_anomaly",
                    severity="medium",
                    title=f"{item.product_name}の単位が通常と異なります",
                    summary=(f"通常は「{stats.typical_unit}」単位ですが、今回は「{item.unit}」で受注しました。"),
                    suggested_action="顧客が意図した単位かどうかを確認してください。",
                    evidence=[
                        Evidence(label="通常単位", value=stats.typical_unit),
                        Evidence(label="今回の単位", value=item.unit),
                    ],
                    metadata={
                        "item_index": index,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "typical_unit": stats.typical_unit,
                        "ordered_unit": item.unit,
                    },
                )
            )
    return cases


async def _classify_inventory(order: Order, tenant_id: str, inventory: Any) -> list[ExceptionCase]:
    cases: list[ExceptionCase] = []
    for index, item in enumerate(order.items):
        required = item.quantity
        if required is None or required <= 0:
            continue
        try:
            status = await inventory.check(tenant_id, item.product_id, required)
        except Exception:  # noqa: BLE001 -- 在庫サービス障害時はスキップ
            continue
        if status.is_sufficient:
            continue
        shortage = max(required - status.available_qty, 0)
        cases.append(
            _build_case(
                order=order,
                case_type="inventory_shortage",
                severity="high",
                title=f"{item.product_name}の在庫不足",
                summary=(
                    f"在庫{status.available_qty:g}{status.unit}に対し、"
                    f"注文{required:g}{item.unit}（不足{shortage:g}{status.unit}）です。"
                ),
                suggested_action="代替品の提案または分納を顧客と調整してください。",
                evidence=[
                    Evidence(label="注文数量", value=f"{required:g}{item.unit}"),
                    Evidence(label="在庫数量", value=f"{status.available_qty:g}{status.unit}"),
                    Evidence(label="不足", value=f"{shortage:g}{status.unit}"),
                ],
                metadata={
                    "item_index": index,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "required_qty": required,
                    "available_qty": status.available_qty,
                    "unit": item.unit,
                },
            )
        )
    return cases


def _quantity_anomaly(item: OrderItem, stats: ProductStats | None) -> dict[str, Any] | None:
    """classify_quantity_anomaly の結果に Evidence リストを付加して返す。"""
    qty = item.quantity
    if qty is None:
        return None
    result = classify_quantity_anomaly(qty, item.unit or "", stats)
    if result is None:
        return None

    # Evidence リストを組み立てる（dashboard_agent 固有の表示用）
    evidence: list[Evidence] = [Evidence(label="今回数量", value=f"{qty:g}{item.unit}")]
    if result["typical_qty"] is not None and result["typical_unit"] is not None:
        evidence.append(Evidence(label="通常数量", value=f"{result['typical_qty']:g}{result['typical_unit']}"))
    if result["z_score"] is not None:
        evidence.append(Evidence(label="Zスコア", value=f"{result['z_score']:.1f}"))

    return {
        "severity": result["severity"],
        "summary": result["summary"],
        "evidence": evidence,
        "z_score": result["z_score"],
    }


def _stats_for(profile: CustomerOrderProfile | None, product_id: str) -> ProductStats | None:
    if profile is None:
        return None
    return profile.product_stats.get(product_id)


async def _safe_get_profile(store: Any, tenant_id: str, customer_id: str) -> CustomerOrderProfile | None:
    try:
        return await store.get_customer_profile(tenant_id, customer_id)
    except Exception:  # noqa: BLE001 -- プロファイル取得失敗時は無いものとして処理
        return None


def _build_case(
    *,
    order: Order,
    case_type: ExceptionCaseType,
    severity: ExceptionSeverity,
    title: str,
    summary: str,
    suggested_action: str,
    evidence: list[Evidence],
    metadata: dict[str, Any] | None = None,
) -> ExceptionCase:
    parts: list[str] = ["exc", order.id, case_type]
    item_index = metadata.get("item_index") if metadata else None
    if item_index is not None:
        parts.append(str(item_index))
    elif evidence:
        parts.append(sha1(evidence[0].value.encode("utf-8")).hexdigest()[:8])
    return ExceptionCase(
        id="-".join(parts),
        order_id=order.id,
        customer_id=order.customer_id,
        customer_name=order.customer_name,
        type=case_type,
        severity=severity,
        title=title,
        summary=summary,
        suggested_action=suggested_action,
        evidence=evidence,
        metadata=metadata or {},
    )


def _preview_quantity_anomaly(case: ExceptionCase) -> ResolutionPreview:
    meta = case.metadata
    product = str(meta.get("product_name") or "該当商品")
    ordered = _coerce_float(meta.get("ordered_qty"))
    typical = _coerce_float(meta.get("typical_qty"))
    unit = str(meta.get("unit") or "")
    typical_unit = str(meta.get("typical_unit") or unit)
    z_score = _coerce_float(meta.get("z_score"))

    proposed = typical if typical is not None else _digit_correction(ordered)
    ordered_label = _format_qty(ordered, unit)
    has_proposal = proposed is not None and ordered is not None and proposed != ordered
    proposed_label = _format_qty(proposed, typical_unit) if has_proposal else ""

    confidence = 0.5
    if z_score is not None:
        confidence = min(0.99, 0.6 + z_score / 20)
    elif typical is not None:
        confidence = 0.7

    actions: list[str] = []
    if has_proposal:
        actions.append(f"数量を {ordered_label} → {proposed_label} に修正する案を顧客へ確認")
    actions.append("顧客の意図を再確認したうえで受注処理をやり直す")

    message_lines = [
        f"{product}を{ordered_label}で承りました。",
    ]
    if has_proposal:
        message_lines.append(f"念のため確認させてください。今回の数量は{proposed_label}のお間違いではないでしょうか？")
    else:
        message_lines.append("念のため、ご注文数量にお間違いがないかご確認ください。")

    if has_proposal:
        summary = f"{product}は通常 {proposed_label} 前後のところ {ordered_label} の受注を検知しました。"
    elif typical is not None:
        summary = f"{product}の {ordered_label} の受注を再確認します。"
    else:
        # プロファイル未蓄積のフォールバック検知。代替値が無いことを明示する。
        summary = (
            f"{product}は過去パターン未蓄積の状態で {ordered_label} の大口受注を検知しました。"
            "桁誤り等の可能性を顧客へ確認してください。"
        )

    return ResolutionPreview(
        exception_id=case.id,
        title="数量異常の確認文案",
        summary=summary,
        confidence=round(confidence, 2),
        recommended_actions=actions,
        customer_message="\n".join(message_lines),
        requires_approval=True,
    )


def _preview_unit_anomaly(case: ExceptionCase) -> ResolutionPreview:
    meta = case.metadata
    product = str(meta.get("product_name") or "該当商品")
    ordered_unit = str(meta.get("ordered_unit") or "")
    typical_unit = str(meta.get("typical_unit") or "")
    return ResolutionPreview(
        exception_id=case.id,
        title="単位の確認文案",
        summary=(f"{product}は通常「{typical_unit}」単位ですが、今回は「{ordered_unit}」で受注しました。"),
        confidence=0.6,
        recommended_actions=[
            f"単位を「{ordered_unit}」→「{typical_unit}」に置換するかを顧客へ確認",
            "修正後の単位で受注内容を再処理する",
        ],
        customer_message=(
            f"{product}は通常「{typical_unit}」単位でご注文いただいておりますが、"
            f"今回は「{ordered_unit}」とのご指定でした。\n"
            "単位のご指定にお間違いがないかご確認ください。"
        ),
        requires_approval=True,
    )


def _preview_inventory_shortage_body(case: ExceptionCase, alternatives: list[dict[str, Any]]) -> ResolutionPreview:
    meta = case.metadata
    product = str(meta.get("product_name") or "該当商品")
    required = _coerce_float(meta.get("required_qty"))
    available = _coerce_float(meta.get("available_qty"))
    unit = str(meta.get("unit") or "")

    actions: list[str] = []
    alternative_names: list[str] = []
    for alt in alternatives:
        alt_label = f"{alt.get('product_name')} ({alt.get('available_qty'):g}{alt.get('unit')})"
        alternative_names.append(alt_label)
        actions.append(f"代替品として {alt_label} を提案")
    if not actions:
        actions.append("代替品が見つからないため、分納または納期調整を顧客と相談")
    actions.append("顧客の返信に応じて正式回答を送信する")

    message_lines = [
        f"{product}を{_format_qty(required, unit)}で承りましたが、現在の在庫は{_format_qty(available, unit)}です。",
    ]
    if alternative_names:
        message_lines.append("代替品として下記をご提案できます：")
        message_lines.extend([f"・{name}" for name in alternative_names])
    message_lines.append("ご希望の対応方法をご返信ください。")

    return ResolutionPreview(
        exception_id=case.id,
        title="在庫不足の代替提案",
        summary=(
            f"{product}は不足のため、{len(alternatives)} 件の代替候補を準備しました。"
            if alternatives
            else f"{product}は不足のため、分納または納期調整の案内を準備しました。"
        ),
        confidence=0.75 if alternatives else 0.55,
        recommended_actions=actions,
        customer_message="\n".join(message_lines),
        requires_approval=True,
    )


def _preview_needs_review(case: ExceptionCase) -> ResolutionPreview:
    return ResolutionPreview(
        exception_id=case.id,
        title="要対応受注の確認文案",
        summary="AIが自動処理を保留した受注です。担当者の確認が必要です。",
        confidence=0.5,
        recommended_actions=[
            "会話履歴と注文内容を確認し、必要な情報を整理",
            "顧客に追加確認が必要ならドラフトを送信",
        ],
        customer_message=("ご注文内容について追加で確認させていただきたい点がございます。担当者が確認します。"),
        requires_approval=True,
    )


def _digit_correction(quantity: float | None) -> float | None:
    """100単位の桁誤りらしい数量を 1/10 にする簡易補正."""
    if quantity is None or quantity < 100:
        return None
    if quantity % 10 != 0:
        return None
    return quantity / 10


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _format_qty(value: float | None, unit: str) -> str:
    if value is None:
        return "現状の数量"
    return f"{value:g}{unit}".strip()
