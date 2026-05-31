"""ダッシュボード Agent 用 FastAPI ルータ.

- GET  /api/agent/features           : 機能フラグ
- GET  /api/agent/exceptions         : 受注一覧の表示条件に合わせた Exception Case 一覧
- POST /api/agent/resolutions/preview: Resolution Agent によるプレビュー
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.auth.dependencies import get_tenant_id
from src.services.dashboard_agent import (
    DashboardAgentService,
    ExceptionCase,
)
from src.services.tenant_resolver import resolve_tenant_by_id

router = APIRouter(prefix="/api/agent", tags=["dashboard-agent"])


class ResolutionPreviewRequest(BaseModel):
    exception_case: ExceptionCase


@router.get("/features")
async def get_agent_features(_tenant_id: str = Depends(get_tenant_id)) -> dict:
    return DashboardAgentService.features().model_dump()


@router.get("/exceptions")
async def list_agent_exceptions(
    delivery_date: date | None = Query(None, description="配送日（YYYY-MM-DD）"),
    order_date: date | None = Query(None, description="受注日（YYYY-MM-DD）"),
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant_id: str = Depends(get_tenant_id),
) -> dict:
    target_date = order_date or delivery_date
    date_field = "order_date" if order_date else "delivery_date"
    features = DashboardAgentService.features()
    if not features.exception_triage:
        return {
            "enabled": False,
            "reason": "feature_disabled",
            "date": target_date.isoformat() if target_date else None,
            "date_field": date_field if target_date else None,
            "cases": [],
        }

    service = DashboardAgentService(resolve_tenant_by_id(tenant_id))
    cases = await service.list_exception_cases_for_order_list(
        tenant_id,
        target_date,
        status=status,
        source=source,
        q=q,
        limit=limit,
        offset=offset,
        date_field=date_field,
    )
    return {
        "enabled": True,
        "date": target_date.isoformat() if target_date else None,
        "date_field": date_field if target_date else None,
        "filters": {
            "status": status,
            "source": source,
            "q": q,
            "limit": limit,
            "offset": offset,
        },
        "cases": [case.model_dump(mode="json") for case in cases],
    }


@router.get("/review-summary")
async def get_review_summary(tenant_id: str = Depends(get_tenant_id)) -> dict:
    """要対応ステータスの総件数を返す（ページング・フィルタ無関係）。バナー表示用。"""
    repo = resolve_tenant_by_id(tenant_id).get_connector("IOrderRepository")
    _, total = await repo.list_orders(tenant_id, status="要対応", limit=1, offset=0)
    return {"needs_review_total": total}


@router.post("/resolutions/preview")
async def preview_agent_resolution(
    request: ResolutionPreviewRequest,
    tenant_id: str = Depends(get_tenant_id),
) -> dict:
    features = DashboardAgentService.features()
    if not features.resolution_agent:
        return {
            "enabled": False,
            "execute_enabled": False,
            "reason": "feature_disabled",
            "preview": None,
        }

    service = DashboardAgentService(resolve_tenant_by_id(tenant_id))
    preview = await service.preview_resolution(request.exception_case)
    return {
        "enabled": True,
        "execute_enabled": features.resolution_execute,
        "preview": preview.model_dump(mode="json"),
    }
