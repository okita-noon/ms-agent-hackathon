from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.auth.dependencies import get_tenant_id
from src.connectors.interfaces.inventory_service import Alternative, InventoryStatus
from src.models.intelligence import CustomerOrderProfile, ProductStats
from src.models.order import (
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    TemperatureZone,
)
from src.services.dashboard_agent import (
    DashboardAgentService,
    ExceptionCase,
    Evidence,
)


def _order(
    *,
    uid: str = "ORD-001",
    status: OrderStatus = OrderStatus.ACCEPTED,
    items: list[OrderItem] | None = None,
    remarks: str | None = None,
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
        items=items
        or [
            OrderItem(
                product_id="P-001",
                product_name="完熟トマト",
                quantity=15,
                unit="kg",
                temperature_zone=TemperatureZone.CHILLED,
            )
        ],
    )


def _inventory_ok() -> AsyncMock:
    svc = AsyncMock()
    svc.check.return_value = InventoryStatus(
        product_id="P-001",
        product_name="完熟トマト",
        available_qty=1000,
        unit="kg",
        is_sufficient=True,
    )
    svc.find_alternatives.return_value = []
    return svc


def _profile_with_tomato(**overrides) -> CustomerOrderProfile:
    base = ProductStats(
        avg_qty=15.0,
        std_dev=5.0,
        min_qty=5.0,
        max_qty=30.0,
        typical_unit="kg",
        total_orders=10,
    )
    stats = base.model_copy(update=overrides)
    return CustomerOrderProfile(
        tenant_id="T-TEST",
        customer_id="C-001",
        product_stats={"P-001": stats},
    )


class TestDashboardAgentClassification:
    @pytest.mark.asyncio
    async def test_z_score_detects_high_severity_quantity_anomaly(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            _order(
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="完熟トマト",
                        quantity=150,
                        unit="kg",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ]
            ),
        ]
        store = ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = _profile_with_tomato()
        ctx._connectors["IInventoryService"] = _inventory_ok()

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        types = [c.type for c in cases]
        assert "quantity_anomaly" in types
        anomaly = next(c for c in cases if c.type == "quantity_anomaly")
        assert anomaly.severity == "high"
        assert anomaly.metadata["z_score"] == pytest.approx(27.0)
        assert any(e.label == "Zスコア" for e in anomaly.evidence)

    @pytest.mark.asyncio
    async def test_z_score_within_threshold_emits_no_case(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            _order(
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="完熟トマト",
                        quantity=20,
                        unit="kg",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ]
            ),
        ]
        store = ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = _profile_with_tomato()
        ctx._connectors["IInventoryService"] = _inventory_ok()

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        assert not any(c.type == "quantity_anomaly" for c in cases)

    @pytest.mark.asyncio
    async def test_unit_anomaly_detected_when_profile_uses_different_unit(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            _order(
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="完熟トマト",
                        quantity=15,
                        unit="箱",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ]
            ),
        ]
        store = ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = _profile_with_tomato()
        ctx._connectors["IInventoryService"] = _inventory_ok()

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        unit_case = next(c for c in cases if c.type == "unit_anomaly")
        assert "通常単位" in [e.label for e in unit_case.evidence]
        assert unit_case.metadata["typical_unit"] == "kg"

    @pytest.mark.asyncio
    async def test_inventory_shortage_uses_check_and_shortage_evidence(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            _order(
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="完熟トマト",
                        quantity=20,
                        unit="kg",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ]
            ),
        ]
        store = ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = _profile_with_tomato()
        inventory = AsyncMock()
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="完熟トマト",
            available_qty=5,
            unit="kg",
            is_sufficient=False,
        )
        ctx._connectors["IInventoryService"] = inventory

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        shortage = next(c for c in cases if c.type == "inventory_shortage")
        assert shortage.severity == "high"
        assert shortage.metadata["required_qty"] == 20
        assert shortage.metadata["available_qty"] == 5
        labels = {e.label for e in shortage.evidence}
        assert {"注文数量", "在庫数量", "不足"} <= labels

    @pytest.mark.asyncio
    async def test_status_review_emits_case(self, mock_tenant_ctx):
        # 「返信待ち」は要対応に統合されたため、要対応ステータスのみが対象
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            _order(uid="ORD-A", status=OrderStatus.NEEDS_REVIEW),
        ]
        ctx.get_connector("IOrderIntelligenceStore").get_customer_profile.return_value = None
        ctx._connectors["IInventoryService"] = _inventory_ok()

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        types_by_order = {(c.order_id, c.type) for c in cases}
        assert ("ORD-A", "needs_review") in types_by_order

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        ctx.get_connector("IOrderRepository").list_by_date.return_value = []

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        assert cases == []

    @pytest.mark.asyncio
    async def test_fallback_quantity_threshold_when_profile_missing(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            _order(
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="完熟トマト",
                        quantity=150,
                        unit="kg",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ]
            ),
        ]
        ctx.get_connector("IOrderIntelligenceStore").get_customer_profile.return_value = None
        ctx._connectors["IInventoryService"] = _inventory_ok()

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        assert any(c.type == "quantity_anomaly" for c in cases)

    @pytest.mark.asyncio
    async def test_terminal_orders_are_skipped_from_triage(self, mock_tenant_ctx):
        ctx = mock_tenant_ctx
        repo = ctx.get_connector("IOrderRepository")
        repo.list_by_date.return_value = [
            # 完了済み：在庫が薄くても triage しない
            _order(
                uid="ORD-DONE",
                status=OrderStatus.COMPLETED,
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="完熟トマト",
                        quantity=150,
                        unit="kg",
                        temperature_zone=TemperatureZone.CHILLED,
                    )
                ],
            ),
            # キャンセル済み：要対応相当に見えても無視
            _order(uid="ORD-CXL", status=OrderStatus.CANCELLED),
            # 通常受注：これだけが triage 対象
            _order(uid="ORD-LIVE", status=OrderStatus.NEEDS_REVIEW),
        ]
        store = ctx.get_connector("IOrderIntelligenceStore")
        store.get_customer_profile.return_value = _profile_with_tomato()
        # 在庫不足を返してくる状態でも、終端ステータスでは inventory.check を呼ばない
        inventory = AsyncMock()
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="完熟トマト",
            available_qty=1,
            unit="kg",
            is_sufficient=False,
        )
        ctx._connectors["IInventoryService"] = inventory

        cases = await DashboardAgentService(ctx).list_exception_cases("T-TEST", date(2026, 5, 20))

        triggered_order_ids = {c.order_id for c in cases}
        assert "ORD-DONE" not in triggered_order_ids
        assert "ORD-CXL" not in triggered_order_ids
        assert "ORD-LIVE" in triggered_order_ids
        # 在庫チェックはライブ受注分のみ呼ばれる（終端2件はスキップ）
        assert inventory.check.call_count == 1


class TestDashboardAgentResolutionPreview:
    @pytest.fixture
    def service(self, mock_tenant_ctx):
        return DashboardAgentService(mock_tenant_ctx)

    @pytest.mark.asyncio
    async def test_quantity_anomaly_proposes_typical_quantity(self, service):
        case = ExceptionCase(
            id="exc-1",
            order_id="ORD-001",
            customer_id="C-001",
            customer_name="テスト食堂",
            type="quantity_anomaly",
            severity="high",
            title="完熟トマトの数量異常",
            summary="通常 15kg 前後のところ 150kg で受注",
            suggested_action="確認",
            evidence=[Evidence(label="今回数量", value="150kg")],
            metadata={
                "product_name": "完熟トマト",
                "ordered_qty": 150,
                "typical_qty": 15,
                "typical_unit": "kg",
                "unit": "kg",
                "z_score": 27.0,
            },
        )

        preview = await service.preview_resolution(case)

        assert preview.confidence > 0.9
        assert any("15kg" in action for action in preview.recommended_actions)
        assert "15kg" in preview.customer_message
        assert preview.requires_approval is True

    @pytest.mark.asyncio
    async def test_quantity_anomaly_preview_without_proposal_avoids_placeholder(self, service):
        # プロファイル無し・桁誤り補正もできない（123 は 10 の倍数ではない）パターン
        case = ExceptionCase(
            id="exc-fb",
            order_id="ORD-FB",
            customer_id="C-001",
            customer_name="テスト食堂",
            type="quantity_anomaly",
            severity="medium",
            title="数量異常",
            summary="フォールバック検知",
            suggested_action="確認",
            evidence=[Evidence(label="今回数量", value="123kg")],
            metadata={
                "product_name": "完熟トマト",
                "ordered_qty": 123,
                "typical_qty": None,
                "typical_unit": "kg",
                "unit": "kg",
                "z_score": None,
            },
        )

        preview = await service.preview_resolution(case)

        # 「現状の数量」プレースホルダがそのまま顧客向け文面に漏れないこと
        assert "現状の数量" not in preview.summary
        assert "現状の数量" not in preview.customer_message
        assert "123kg" in preview.summary
        # 修正提案ができない場合、recommended_actions に「→」差分提案は出ない
        assert not any("→" in action for action in preview.recommended_actions)

    @pytest.mark.asyncio
    async def test_inventory_shortage_pulls_alternatives_from_connector(self, mock_tenant_ctx):
        inventory = AsyncMock()
        inventory.find_alternatives.return_value = [
            Alternative(
                product_id="P-002",
                product_name="ミニトマト",
                available_qty=20,
                unit="kg",
                similarity_score=0.8,
            )
        ]
        mock_tenant_ctx._connectors["IInventoryService"] = inventory

        case = ExceptionCase(
            id="exc-2",
            order_id="ORD-002",
            customer_id="C-001",
            customer_name="テスト食堂",
            type="inventory_shortage",
            severity="high",
            title="完熟トマトの在庫不足",
            summary="不足",
            suggested_action="代替提案",
            evidence=[Evidence(label="不足", value="15kg")],
            metadata={
                "product_id": "P-001",
                "product_name": "完熟トマト",
                "required_qty": 20,
                "available_qty": 5,
                "unit": "kg",
            },
        )

        preview = await DashboardAgentService(mock_tenant_ctx).preview_resolution(case)

        inventory.find_alternatives.assert_awaited_once_with("T-TEST", "P-001", 20)
        assert "ミニトマト" in preview.customer_message
        assert any("ミニトマト" in action for action in preview.recommended_actions)


class TestDashboardAgentApi:
    @pytest.fixture
    def client(self):
        app.dependency_overrides[get_tenant_id] = lambda: "T-TEST"
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.clear()

    def test_features_returns_flags(self, client):
        with patch.dict(
            "os.environ",
            {
                "DASHBOARD_AGENT_ENABLED": "true",
                "DASHBOARD_EXCEPTION_TRIAGE_ENABLED": "true",
                "DASHBOARD_RESOLUTION_AGENT_ENABLED": "true",
                "DASHBOARD_RESOLUTION_EXECUTE_ENABLED": "false",
                "DASHBOARD_AGENT_DEMO_MODE": "false",
            },
        ):
            resp = client.get("/api/agent/features")

        assert resp.status_code == 200
        assert resp.json() == {
            "dashboard_agent": True,
            "exception_triage": True,
            "resolution_agent": True,
            "resolution_execute": False,
            "demo_mode": False,
        }

    def test_exceptions_disabled_when_feature_off(self, client):
        with (
            patch.dict("os.environ", {"DASHBOARD_AGENT_ENABLED": "false"}),
            patch("src.api.dashboard_agent.resolve_tenant_by_id") as resolve,
        ):
            resp = client.get("/api/agent/exceptions")

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["date"] is None
        assert body["date_field"] is None
        assert body["cases"] == []
        resolve.assert_not_called()

    def test_exceptions_resolves_tenant_and_returns_cases_for_current_order_list(self, client):
        repo = AsyncMock()
        repo.list_orders.return_value = ([_order(status=OrderStatus.NEEDS_REVIEW)], 1)
        store = AsyncMock()
        store.get_customer_profile.return_value = None
        inventory = _inventory_ok()

        tenant_ctx = MagicMock()
        tenant_ctx.tenant_id = "T-TEST"
        tenant_ctx.get_connector.side_effect = lambda name: {
            "IOrderRepository": repo,
            "IOrderIntelligenceStore": store,
            "IInventoryService": inventory,
        }[name]

        with (
            patch.dict(
                "os.environ",
                {
                    "DASHBOARD_AGENT_ENABLED": "true",
                    "DASHBOARD_EXCEPTION_TRIAGE_ENABLED": "true",
                },
            ),
            patch(
                "src.api.dashboard_agent.resolve_tenant_by_id",
                return_value=tenant_ctx,
            ) as resolve,
        ):
            resp = client.get("/api/agent/exceptions?status=要対応&q=テスト&limit=25&offset=50")

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["date"] is None
        assert body["date_field"] is None
        assert body["filters"] == {
            "status": "要対応",
            "source": None,
            "q": "テスト",
            "limit": 25,
            "offset": 50,
        }
        assert body["cases"][0]["type"] == "needs_review"
        resolve.assert_called_once_with("T-TEST")
        repo.list_orders.assert_awaited_once_with(
            "T-TEST",
            None,
            status="要対応",
            source=None,
            q="テスト",
            limit=25,
            offset=50,
            date_field="delivery_date",
        )

    def test_exceptions_uses_order_date_filter_when_requested(self, client):
        repo = AsyncMock()
        repo.list_orders.return_value = ([_order(status=OrderStatus.NEEDS_REVIEW)], 1)
        store = AsyncMock()
        store.get_customer_profile.return_value = None
        inventory = _inventory_ok()

        tenant_ctx = MagicMock()
        tenant_ctx.tenant_id = "T-TEST"
        tenant_ctx.get_connector.side_effect = lambda name: {
            "IOrderRepository": repo,
            "IOrderIntelligenceStore": store,
            "IInventoryService": inventory,
        }[name]

        with (
            patch.dict(
                "os.environ",
                {
                    "DASHBOARD_AGENT_ENABLED": "true",
                    "DASHBOARD_EXCEPTION_TRIAGE_ENABLED": "true",
                },
            ),
            patch("src.api.dashboard_agent.resolve_tenant_by_id", return_value=tenant_ctx),
        ):
            resp = client.get("/api/agent/exceptions?order_date=2026-05-20&limit=50&offset=0")

        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-05-20"
        assert body["date_field"] == "order_date"
        repo.list_orders.assert_awaited_once_with(
            "T-TEST",
            date(2026, 5, 20),
            status=None,
            source=None,
            q=None,
            limit=50,
            offset=0,
            date_field="order_date",
        )

    def test_preview_disabled_when_resolution_off(self, client):
        payload = {
            "exception_case": {
                "id": "exc-1",
                "order_id": "ORD-001",
                "customer_id": "C-001",
                "customer_name": "テスト食堂",
                "type": "needs_review",
                "severity": "high",
                "title": "要対応",
                "summary": "確認",
                "suggested_action": "確認",
                "evidence": [],
                "metadata": {},
            }
        }
        with patch.dict(
            "os.environ",
            {
                "DASHBOARD_AGENT_ENABLED": "true",
                "DASHBOARD_RESOLUTION_AGENT_ENABLED": "false",
            },
        ):
            resp = client.post("/api/agent/resolutions/preview", json=payload)

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["preview"] is None
