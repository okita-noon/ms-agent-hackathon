from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.message_history import MessageHistory
from src.models.order import Order, OrderSource


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "foogent-api"


class TestRootRedirect:
    def test_redirects_to_dashboard(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert "/dashboard" in resp.headers["location"]

    def test_legacy_dashboard_path_redirects_to_dashboard(self, client):
        resp = client.get("/dashboard/", follow_redirects=False)
        assert resp.status_code == 307
        assert "/dashboard" in resp.headers["location"]


class TestLineWebhook:
    def test_returns_200_for_valid_request(self, client):
        with (
            patch("src.api.main.resolve_tenant_for_line") as mock_resolve,
            patch("src.api.main.LineWebhookHandler") as mock_handler_cls,
        ):
            from unittest.mock import MagicMock

            mock_ctx = MagicMock()
            mock_ctx.config.line_channel_secret = None
            mock_resolve.return_value = mock_ctx

            mock_handler = MagicMock()
            mock_handler.verify_signature.return_value = True
            mock_handler_cls.return_value = mock_handler

            resp = client.post(
                "/api/line-webhook",
                json={"events": []},
                headers={"x-line-signature": "test"},
            )
            assert resp.status_code == 200

    def test_rejects_invalid_signature(self, client):
        with (
            patch("src.api.main.resolve_tenant_for_line") as mock_resolve,
            patch("src.api.main.LineWebhookHandler") as mock_handler_cls,
        ):
            mock_ctx = MagicMock()
            mock_resolve.return_value = mock_ctx

            mock_handler = MagicMock()
            mock_handler.verify_signature.return_value = False
            mock_handler_cls.return_value = mock_handler

            resp = client.post(
                "/api/line-webhook",
                json={"events": []},
                headers={"x-line-signature": "bad-sig"},
            )
            assert resp.status_code == 403

    def test_rejects_missing_signature_header(self, client):
        """The signature header is mandatory; missing it must yield 401."""
        resp = client.post("/api/line-webhook", json={"events": []})
        assert resp.status_code == 401


class TestPhoneWebhook:
    def test_rejects_when_key_not_configured(self, client):
        with patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": ""}):
            resp = client.post("/api/phone-webhook", json=[])
            assert resp.status_code == 401

    def test_rejects_wrong_key(self, client):
        with patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": "expected"}):
            resp = client.post(
                "/api/phone-webhook",
                json=[],
                headers={"X-EventGrid-Webhook-Key": "wrong"},
            )
            assert resp.status_code == 401

    def test_accepts_correct_key_header(self, client):
        with patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": "expected"}):
            resp = client.post(
                "/api/phone-webhook",
                json=[],
                headers={"X-EventGrid-Webhook-Key": "expected"},
            )
            assert resp.status_code == 200

    def test_accepts_correct_key_query_param(self, client):
        with patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": "expected"}):
            resp = client.post("/api/phone-webhook?code=expected", json=[])
            assert resp.status_code == 200

    def test_subscription_validation_requires_key(self, client):
        """Even the EventGrid subscription validation handshake must auth."""
        validation_event = [
            {
                "type": "Microsoft.EventGrid.SubscriptionValidationEvent",
                "data": {"validationCode": "abc"},
            }
        ]
        with patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": "expected"}):
            resp = client.post("/api/phone-webhook", json=validation_event)
            assert resp.status_code == 401
            resp = client.post(
                "/api/phone-webhook",
                json=validation_event,
                headers={"X-EventGrid-Webhook-Key": "expected"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"validationResponse": "abc"}


class TestPhoneDemoMessage:
    def test_rejects_when_key_not_configured(self, client):
        with patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": ""}):
            resp = client.post("/api/phone-demo/message", json={"message": "りんご10箱"})
            assert resp.status_code == 401

    def test_processes_demo_message_with_correct_key(self, client):
        mock_handler = MagicMock()
        mock_handler.process_demo_message = AsyncMock(
            return_value={
                "demo_mode": True,
                "call_connection_id": "demo-12345678",
                "status": "processed",
                "order_id": "ORD-DEMO",
                "response": "りんご10箱、承りました。",
            }
        )
        mock_handler.disconnect_demo_call = AsyncMock(return_value={"status": "disconnected"})

        with (
            patch.dict("os.environ", {"EVENTGRID_WEBHOOK_KEY": "expected"}),
            patch("src.api.main._get_phone_handler", return_value=mock_handler),
        ):
            resp = client.post(
                "/api/phone-demo/message?code=expected",
                json={
                    "message": "りんご10箱",
                    "caller_number": "+81312345678",
                    "called_number": "+81501234567",
                    "disconnect": True,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["order_id"] == "ORD-DEMO"
        mock_handler.process_demo_message.assert_awaited_once_with(
            message="りんご10箱",
            caller_number="+81312345678",
            called_number="+81501234567",
            call_connection_id=None,
        )
        mock_handler.disconnect_demo_call.assert_awaited_once_with("demo-12345678")


class TestOrderMessages:
    @pytest.mark.asyncio
    async def test_get_order_messages_uses_tenant_scoped_order_lookup(self):
        from src.api.main import get_order_messages

        order = Order(
            uid="ORD-001",
            tenant_id="T-001",
            order_date=date(2026, 5, 18),
            customer_id="C-001",
            customer_name="テスト社",
            source=OrderSource.LINE,
            session_id="sess-1",
        )
        messages = [
            MessageHistory(
                id="hist-user",
                tenant_id="T-001",
                session_id="sess-1",
                channel="line",
                channel_user_id="U123",
                role="user",
                text="りんご1箱",
                created_at=datetime(2026, 5, 18, 9, 0),
            ),
            MessageHistory(
                id="hist-system",
                tenant_id="T-001",
                session_id="sess-1",
                channel="line",
                channel_user_id="U123",
                role="system",
                text="internal",
                created_at=datetime(2026, 5, 18, 9, 1),
            ),
        ]

        order_repo = MagicMock()
        order_repo.find_by_id = AsyncMock(return_value=order)
        history_repo = MagicMock()
        history_repo.list_by_session_id = AsyncMock(return_value=messages)
        tenant_ctx = MagicMock()
        tenant_ctx.get_connector.side_effect = {
            "IOrderRepository": order_repo,
            "IMessageHistoryRepository": history_repo,
        }.__getitem__

        with patch("src.api.main.resolve_tenant_by_id", return_value=tenant_ctx):
            result = await get_order_messages("ORD-001", tenant_id="T-001")

        order_repo.find_by_id.assert_awaited_once_with("T-001", "ORD-001")
        history_repo.list_by_session_id.assert_awaited_once_with("T-001", "sess-1")
        assert result["session_id"] == "sess-1"
        assert [message["id"] for message in result["messages"]] == ["hist-user"]
