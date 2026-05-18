from __future__ import annotations

import os
from datetime import date
from hashlib import sha1
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.connectors.context import TenantContext
from src.models.order import Order, OrderStatus


TRUTHY = {"1", "true", "yes", "on", "enabled"}
INVENTORY_SHORTAGE_KEYWORDS = ("在庫不足",)
CONFIRMATION_KEYWORDS = ("異常", "確認")
QUANTITY_ANOMALY_THRESHOLD = 100
ExceptionCaseType = Literal[
    "status_review",
    "awaiting_reply",
    "inventory_shortage",
    "confirmation_required",
    "quantity_anomaly",
]
ExceptionSeverity = Literal["low", "medium", "high"]
Numeric = int | float


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY


class AgentFeatures(BaseModel):
    dashboard_agent: bool
    exception_triage: bool
    resolution_agent: bool
    resolution_execute: bool
    demo_mode: bool


class CustomerSummary(BaseModel):
    id: str
    name: str


class ExceptionCase(BaseModel):
    id: str
    order_id: str
    customer: CustomerSummary
    type: ExceptionCaseType
    severity: ExceptionSeverity
    title: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    suggested_action: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProposedAction(BaseModel):
    type: str
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionPreview(BaseModel):
    summary: str
    proposed_actions: list[ProposedAction]
    customer_message: str
    requires_approval: bool = True


class DashboardAgentService:
    def __init__(self, tenant_ctx: TenantContext) -> None:
        self._tenant_ctx = tenant_ctx

    @staticmethod
    def features() -> AgentFeatures:
        dashboard_agent = env_flag("DASHBOARD_AGENT_ENABLED")
        return AgentFeatures(
            dashboard_agent=dashboard_agent,
            exception_triage=dashboard_agent and env_flag("DASHBOARD_EXCEPTION_TRIAGE_ENABLED"),
            resolution_agent=dashboard_agent and env_flag("DASHBOARD_RESOLUTION_AGENT_ENABLED"),
            resolution_execute=dashboard_agent and env_flag("DASHBOARD_RESOLUTION_EXECUTE_ENABLED"),
            demo_mode=env_flag("DASHBOARD_AGENT_DEMO_MODE"),
        )

    async def list_exception_cases(self, tenant_id: str, delivery_date: date) -> list[ExceptionCase]:
        repo = self._tenant_ctx.get_connector("IOrderRepository")
        orders = await repo.list_by_date(tenant_id, delivery_date)
        cases: list[ExceptionCase] = []
        for order in orders:
            cases.extend(_classify_order(order))
        return cases

    def preview_resolution(self, exception_case: ExceptionCase) -> ResolutionPreview:
        if exception_case.type == "quantity_anomaly":
            return _quantity_anomaly_preview(exception_case)
        if exception_case.type == "inventory_shortage":
            return _inventory_shortage_preview(exception_case)
        if exception_case.type == "awaiting_reply":
            return _awaiting_reply_preview(exception_case)
        return _generic_preview(exception_case)


def _classify_order(order: Order) -> list[ExceptionCase]:
    cases: list[ExceptionCase] = []
    if order.status == OrderStatus.NEEDS_REVIEW:
        cases.append(
            _case(
                order=order,
                case_type="status_review",
                severity="high",
                title="担当者確認が必要な受注",
                reason="受注ステータスが「要対応」です。",
                evidence=[f"status={order.status.value}"],
                suggested_action="受注内容を確認し、必要に応じて顧客へ確認してください。",
            )
        )
    elif order.status == OrderStatus.AWAITING_REPLY:
        cases.append(
            _case(
                order=order,
                case_type="awaiting_reply",
                severity="medium",
                title="顧客返信待ちの受注",
                reason="受注ステータスが「返信待ち」です。",
                evidence=[f"status={order.status.value}"],
                suggested_action=(
                    "未回答の確認事項を整理し、リマインド文面を送信してください。"
                ),
            )
        )

    remarks = _collect_remarks(order)
    for remark in remarks:
        if any(keyword in remark for keyword in INVENTORY_SHORTAGE_KEYWORDS):
            cases.append(
                _case(
                    order=order,
                    case_type="inventory_shortage",
                    severity="high",
                    title="在庫不足の可能性",
                    reason="受注メモに在庫不足を示す表現があります。",
                    evidence=[remark],
                    suggested_action=(
                        "在庫状況を確認し、代替品または分納案を提示してください。"
                    ),
                )
            )
        elif any(keyword in remark for keyword in CONFIRMATION_KEYWORDS):
            cases.append(
                _case(
                    order=order,
                    case_type="confirmation_required",
                    severity="medium",
                    title="確認が必要な受注メモ",
                    reason="受注メモに異常または確認を示す表現があります。",
                    evidence=[remark],
                    suggested_action=(
                        "メモの内容を確認し、必要事項を顧客へ問い合わせてください。"
                    ),
                )
            )

    for index, item in enumerate(order.items):
        if item.quantity is not None and item.quantity >= QUANTITY_ANOMALY_THRESHOLD:
            cases.append(
                _case(
                    order=order,
                    case_type="quantity_anomaly",
                    severity="high",
                    title="数量異常の可能性",
                    reason=(
                        "過去プロファイルがないため、"
                        "100以上の数量を明らかな異常候補として検出しました。"
                    ),
                    evidence=[f"{item.product_name}: {item.quantity:g}{item.unit}"],
                    suggested_action=(
                        "桁誤りの可能性を確認し、"
                        "必要であれば修正案を顧客へ確認してください。"
                    ),
                    metadata={
                        "item_index": index,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "unit": item.unit,
                    },
                )
            )

    return cases


def _case(
    *,
    order: Order,
    case_type: ExceptionCaseType,
    severity: ExceptionSeverity,
    title: str,
    reason: str,
    evidence: list[str],
    suggested_action: str,
    metadata: dict[str, Any] | None = None,
) -> ExceptionCase:
    suffix = len(evidence[0]) if evidence else 0
    item_suffix = metadata.get("item_index") if metadata else None
    case_id_parts = ["exc", order.id, str(case_type)]
    if item_suffix is not None:
        case_id_parts.append(str(item_suffix))
    elif suffix:
        case_id_parts.append(sha1(evidence[0].encode("utf-8")).hexdigest()[:8])
    return ExceptionCase(
        id="-".join(case_id_parts),
        order_id=order.id,
        customer=CustomerSummary(id=order.customer_id, name=order.customer_name),
        type=case_type,
        severity=severity,
        title=title,
        reason=reason,
        evidence=evidence,
        suggested_action=suggested_action,
        metadata=metadata or {},
    )


def _collect_remarks(order: Order) -> list[str]:
    remarks: list[str] = []
    if order.remarks:
        remarks.append(order.remarks)
    for item in order.items:
        if item.remarks:
            remarks.append(f"{item.product_name}: {item.remarks}")
    return remarks


def _quantity_anomaly_preview(exception_case: ExceptionCase) -> ResolutionPreview:
    metadata = exception_case.metadata
    product_name = str(metadata.get("product_name") or "該当商品")
    unit = str(metadata.get("unit") or "")
    quantity = metadata.get("quantity")
    proposed_quantity = _demo_quantity_fix(quantity)
    quantity_label = f"{quantity:g}{unit}" if isinstance(quantity, Numeric) else "現在の数量"
    proposed_label = f"{proposed_quantity:g}{unit}" if proposed_quantity is not None else "通常数量"
    return ResolutionPreview(
        summary=(
            f"{product_name}の数量が通常より大きいため、"
            "桁誤り確認のプレビューを作成しました。"
        ),
        proposed_actions=[
            ProposedAction(
                type="update_quantity",
                label=f"{quantity_label}を{proposed_label}として確認",
                payload={
                    "order_id": exception_case.order_id,
                    "product_name": product_name,
                    "current_quantity": quantity,
                    "proposed_quantity": proposed_quantity,
                    "unit": unit,
                },
            ),
            ProposedAction(
                type="send_customer_confirmation",
                label="顧客へ数量確認メッセージを送る",
                payload={"order_id": exception_case.order_id},
            ),
        ],
        customer_message=(
            f"{exception_case.customer.name} 様\n"
            f"{product_name}の数量が{quantity_label}で承っています。"
            f"念のため、{proposed_label}のご注文でお間違いないかご確認ください。"
        ),
    )


def _inventory_shortage_preview(exception_case: ExceptionCase) -> ResolutionPreview:
    alternatives = exception_case.metadata.get("alternatives") or []
    if alternatives:
        alternative_text = "、".join(str(item) for item in alternatives)
        message_tail = f"代替品として{alternative_text}をご提案可能です。"
    else:
        alternative_text = "代替品または分納"
        message_tail = "代替品または分納でのご対応が可能か確認いたします。"
    return ResolutionPreview(
        summary="在庫不足候補に対する顧客確認メッセージのプレビューを作成しました。",
        proposed_actions=[
            ProposedAction(
                type="propose_alternative",
                label=f"{alternative_text}を提案",
                payload={"order_id": exception_case.order_id, "alternatives": alternatives},
            ),
            ProposedAction(
                type="send_customer_confirmation",
                label="顧客へ代替案確認メッセージを送る",
                payload={"order_id": exception_case.order_id},
            ),
        ],
        customer_message=(
            f"{exception_case.customer.name} 様\n"
            f"ご注文商品の在庫を確認しております。{message_tail}"
        ),
    )


def _awaiting_reply_preview(exception_case: ExceptionCase) -> ResolutionPreview:
    return ResolutionPreview(
        summary="返信待ち受注に対するリマインド文面のプレビューを作成しました。",
        proposed_actions=[
            ProposedAction(
                type="send_reminder",
                label="顧客へ確認リマインドを送る",
                payload={"order_id": exception_case.order_id},
            )
        ],
        customer_message=(
            f"{exception_case.customer.name} 様\n"
            "先ほどの確認事項について、ご都合のよい時にご返信ください。"
        ),
    )


def _generic_preview(exception_case: ExceptionCase) -> ResolutionPreview:
    return ResolutionPreview(
        summary=f"{exception_case.title}に対する確認文面のプレビューを作成しました。",
        proposed_actions=[
            ProposedAction(
                type="send_customer_confirmation",
                label="顧客へ確認メッセージを送る",
                payload={"order_id": exception_case.order_id, "case_id": exception_case.id},
            )
        ],
        customer_message=(
            f"{exception_case.customer.name} 様\n"
            "ご注文内容について確認したい点がございます。"
            "詳細を確認のうえご連絡いたします。"
        ),
    )


def _demo_quantity_fix(quantity: Any) -> float | None:
    if not isinstance(quantity, Numeric):
        return None
    if quantity >= 100 and quantity % 10 == 0:
        return quantity / 10
    return None
