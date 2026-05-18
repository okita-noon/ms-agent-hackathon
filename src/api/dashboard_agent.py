"""ダッシュボード Agent 用 FastAPI ルータ.

- GET  /api/agent/features           : 機能フラグ
- GET  /api/agent/exceptions         : 配送日単位の Exception Case 一覧
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
    delivery_date: date = Query(..., description="配送日（YYYY-MM-DD）"),
    tenant_id: str = Depends(get_tenant_id),
) -> dict:
    features = DashboardAgentService.features()
    if not features.exception_triage:
        return {
            "enabled": False,
            "reason": "feature_disabled",
            "delivery_date": delivery_date.isoformat(),
            "cases": [],
        }

    service = DashboardAgentService(resolve_tenant_by_id(tenant_id))
    cases = await service.list_exception_cases(tenant_id, delivery_date)
    return {
        "enabled": True,
        "delivery_date": delivery_date.isoformat(),
        "cases": [case.model_dump(mode="json") for case in cases],
    }


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
