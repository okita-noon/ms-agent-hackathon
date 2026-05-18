from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.dependencies import get_tenant_id
from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.services.dashboard_agent import DashboardAgentService, ExceptionCase


@pytest.fixture
def dashboard_client():
    app.dependency_overrides[get_tenant_id] = lambda: "T-TEST"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _order(
    *,
    uid: str = "ORD-001",
    status: OrderStatus = OrderStatus.PENDING,
    remarks: str | None = None,
    quantity: float | None = 10,
    unit: str = "kg",
    item_remarks: str | None = None,
) -> Order:
    return Order(
        uid=uid,
        tenant_id="T-TEST",
        order_date=date(2026, 5, 18),
        delivery_date=date(2026, 5, 20),
        customer_id="C-001",
        customer_name="テスト食堂",
        source=OrderSource.LINE,
        status=status,
        remarks=remarks,
        items=[
            OrderItem(
                product_id="P-001",
                product_name="冷凍えび",
                quantity=quantity,
                unit=unit,
                temperature_zone=TemperatureZone.FROZEN,
                remarks=item_remarks,
            )
        ],
    )


class TestDashboardAgentService:
    @pytest.mark.asyncio
    async def test_classifies_status_remarks_and_quantity_anomaly(self):
        repo = MagicMock()
        repo.list_by_date = AsyncMock(
            return_value=[
                _order(status=OrderStatus.NEEDS_REVIEW, remarks="在庫不足のため確認", quantity=150),
                _order(
                    uid="ORD-002",
                    status=OrderStatus.AWAITING_REPLY,
                    item_remarks="数量異常の可能性",
                    quantity=5,
                ),
            ]
        )
        tenant_ctx = MagicMock()
        tenant_ctx.get_connector.return_value = repo

        service = DashboardAgentService(tenant_ctx)
        cases = await service.list_exception_cases("T-TEST", date(2026, 5, 20))

        repo.list_by_date.assert_awaited_once_with("T-TEST", date(2026, 5, 20))
        case_types = [case.type for case in cases]
        assert "status_review" in case_types
        assert "inventory_shortage" in case_types
        assert "quantity_anomaly" in case_types
        assert "awaiting_reply" in case_types
        assert "confirmation_required" in case_types
        quantity_case = next(case for case in cases if case.type == "quantity_anomaly")
        assert quantity_case.metadata["quantity"] == 150
        assert quantity_case.suggested_action

    def test_quantity_anomaly_preview_proposes_demo_digit_fix(self):
        service = DashboardAgentService(MagicMock())
        case = ExceptionCase(
            id="exc-1",
            order_id="ORD-001",
            customer={"id": "C-001", "name": "テスト食堂"},
            type="quantity_anomaly",
            severity="high",
            title="数量異常の可能性",
            reason="100以上",
            evidence=["冷凍えび: 150kg"],
            suggested_action="確認",
            metadata={"product_name": "冷凍えび", "quantity": 150, "unit": "kg"},
        )

        preview = service.preview_resolution(case)

        assert preview.requires_approval is True
        assert preview.proposed_actions[0].payload["proposed_quantity"] == 15
        assert "15kg" in preview.customer_message


class TestDashboardAgentApi:
    def test_features_always_works(self, dashboard_client):
        with patch.dict(
            "os.environ",
            {
                "DASHBOARD_AGENT_ENABLED": "true",
                "DASHBOARD_EXCEPTION_TRIAGE_ENABLED": "true",
                "DASHBOARD_RESOLUTION_AGENT_ENABLED": "false",
                "DASHBOARD_RESOLUTION_EXECUTE_ENABLED": "false",
                "DASHBOARD_AGENT_DEMO_MODE": "true",
            },
        ):
            resp = dashboard_client.get("/api/agent/features")

        assert resp.status_code == 200
        assert resp.json() == {
            "dashboard_agent": True,
            "exception_triage": True,
            "resolution_agent": False,
            "resolution_execute": False,
            "demo_mode": True,
        }

    def test_exceptions_return_feature_disabled_when_flag_off(self, dashboard_client):
        with (
            patch.dict("os.environ", {"DASHBOARD_AGENT_ENABLED": "false"}),
            patch("src.api.dashboard_agent.resolve_tenant_by_id") as resolve,
        ):
            resp = dashboard_client.get("/api/agent/exceptions?delivery_date=2026-05-20")

        assert resp.status_code == 200
        assert resp.json() == {"enabled": False, "reason": "feature_disabled", "cases": []}
        resolve.assert_not_called()

    def test_exceptions_use_tenant_repo_when_enabled(self, dashboard_client):
        repo = MagicMock()
        repo.list_by_date = AsyncMock(return_value=[_order(status=OrderStatus.NEEDS_REVIEW)])
        tenant_ctx = MagicMock()
        tenant_ctx.get_connector.return_value = repo

        with (
            patch.dict(
                "os.environ",
                {
                    "DASHBOARD_AGENT_ENABLED": "true",
                    "DASHBOARD_EXCEPTION_TRIAGE_ENABLED": "true",
                },
            ),
            patch("src.api.dashboard_agent.resolve_tenant_by_id", return_value=tenant_ctx) as resolve,
        ):
            resp = dashboard_client.get("/api/agent/exceptions?delivery_date=2026-05-20")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["delivery_date"] == "2026-05-20"
        assert data["cases"][0]["type"] == "status_review"
        resolve.assert_called_once_with("T-TEST")
        repo.list_by_date.assert_awaited_once_with("T-TEST", date(2026, 5, 20))

    def test_resolution_preview_returns_feature_disabled_when_flag_off(self, dashboard_client):
        payload = {
            "exception_case": {
                "id": "exc-1",
                "order_id": "ORD-001",
                "customer": {"id": "C-001", "name": "テスト食堂"},
                "type": "inventory_shortage",
                "severity": "high",
                "title": "在庫不足",
                "reason": "メモ",
                "evidence": ["在庫不足"],
                "suggested_action": "代替提案",
            }
        }
        with patch.dict(
            "os.environ",
            {
                "DASHBOARD_AGENT_ENABLED": "true",
                "DASHBOARD_RESOLUTION_AGENT_ENABLED": "false",
            },
        ):
            resp = dashboard_client.post("/api/agent/resolutions/preview", json=payload)

        assert resp.status_code == 200
        assert resp.json() == {"enabled": False, "reason": "feature_disabled", "preview": None}

    def test_resolution_preview_inventory_shortage_with_alternatives(self, dashboard_client):
        payload = {
            "exception_case": {
                "id": "exc-1",
                "order_id": "ORD-001",
                "customer": {"id": "C-001", "name": "テスト食堂"},
                "type": "inventory_shortage",
                "severity": "high",
                "title": "在庫不足",
                "reason": "メモ",
                "evidence": ["在庫不足"],
                "suggested_action": "代替提案",
                "metadata": {"alternatives": ["冷凍いか", "むきえび"]},
            }
        }
        with (
            patch.dict(
                "os.environ",
                {
                    "DASHBOARD_AGENT_ENABLED": "true",
                    "DASHBOARD_RESOLUTION_AGENT_ENABLED": "true",
                    "DASHBOARD_RESOLUTION_EXECUTE_ENABLED": "false",
                },
            ),
            patch("src.api.dashboard_agent.resolve_tenant_by_id", return_value=MagicMock()),
        ):
            resp = dashboard_client.post("/api/agent/resolutions/preview", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["execute_enabled"] is False
        assert data["preview"]["requires_approval"] is True
        assert "冷凍いか" in data["preview"]["customer_message"]
