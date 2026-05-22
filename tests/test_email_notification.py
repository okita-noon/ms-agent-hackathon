"""受注確認メール機能のテスト.

テスト対象:
  1. CommunicationPlugin.send_order_confirmation_email
  2. GraphEmailService.send_email
  3. Orchestrator の受注確定→メール送信フロー

実行方法:
  pytest tests/test_email_notification.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.customer import Customer, CustomerDeliveryPreference
from src.models.tenant import ConnectorConfig
from src.plugins.communication_plugin import CommunicationPlugin, _build_order_confirmation_html


# ── 1. メールHTML生成のテスト ──────────────────────────────────────────


class TestBuildOrderConfirmationHtml:
    """メール本文HTMLが正しく生成されるか."""

    def test_basic_html(self):
        html = _build_order_confirmation_html(
            customer_name="株式会社テスト",
            order_id="ORD-001",
            items_summary="りんご10箱、バナナ5kg",
            delivery_date="2026-05-22",
            delivery_time_slot="午前中",
        )
        assert "株式会社テスト" in html
        assert "ORD-001" in html
        assert "りんご10箱" in html
        assert "バナナ5kg" in html
        assert "2026-05-22" in html
        assert "午前中" in html
        assert "受注確認" in html

    def test_no_delivery_info(self):
        html = _build_order_confirmation_html(
            customer_name="テスト社",
            order_id="ORD-002",
            items_summary="メロン2玉",
            delivery_date="",
            delivery_time_slot="",
        )
        assert "配送予定日" not in html
        assert "配送時間帯" not in html
        assert "メロン2玉" in html

    def test_single_item(self):
        html = _build_order_confirmation_html(
            customer_name="テスト社",
            order_id="ORD-003",
            items_summary="スイカ1個",
            delivery_date="",
            delivery_time_slot="",
        )
        assert "<li>スイカ1個</li>" in html


# ── 2. CommunicationPlugin メール送信のテスト ─────────────────────────


class TestCommunicationPluginEmail:
    """CommunicationPlugin.send_order_confirmation_email の動作確認."""

    @pytest.mark.asyncio
    async def test_send_email_success(self, mock_tenant_ctx, sample_customer):
        """顧客にメールアドレスがある場合、メールが送信される."""
        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.get_by_id.return_value = sample_customer

        email_service = mock_tenant_ctx.get_connector("IEmailService")
        email_service.send_email.return_value = {"success": True}

        plugin = CommunicationPlugin(mock_tenant_ctx)
        result = await plugin.send_order_confirmation_email(
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_id="ORD-001",
            items_summary="りんご10箱",
            delivery_date="2026-05-22",
            delivery_time_slot="午前中",
        )

        assert result["success"] is True
        email_service.send_email.assert_called_once()
        call_args = email_service.send_email.call_args
        assert call_args.kwargs["to_address"] == "test@example.com"
        assert "ORD-001" in call_args.kwargs["subject"]

    @pytest.mark.asyncio
    async def test_skip_when_no_email(self, mock_tenant_ctx, sample_customer):
        """顧客にメールアドレスがない場合、スキップされる."""
        sample_customer.email = None
        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.get_by_id.return_value = sample_customer

        plugin = CommunicationPlugin(mock_tenant_ctx)
        result = await plugin.send_order_confirmation_email(
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_id="ORD-001",
            items_summary="りんご10箱",
        )

        assert result["success"] is False
        assert "no email" in result["error"]

    @pytest.mark.asyncio
    async def test_skip_when_customer_not_found(self, mock_tenant_ctx):
        """顧客が見つからない場合、スキップされる."""
        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.get_by_id.return_value = None

        plugin = CommunicationPlugin(mock_tenant_ctx)
        result = await plugin.send_order_confirmation_email(
            customer_id="C-999",
            customer_name="存在しない会社",
            order_id="ORD-001",
            items_summary="りんご10箱",
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_skip_when_email_service_not_configured(self, mock_tenant_ctx, sample_customer):
        """IEmailService が未設定の場合、スキップされる."""
        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.get_by_id.return_value = sample_customer

        original_get = mock_tenant_ctx.get_connector

        def _get_connector_raise_on_email(name):
            if name == "IEmailService":
                raise ValueError("No connector config for IEmailService")
            return original_get(name)

        mock_tenant_ctx.get_connector = _get_connector_raise_on_email

        plugin = CommunicationPlugin(mock_tenant_ctx)
        result = await plugin.send_order_confirmation_email(
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_id="ORD-001",
            items_summary="りんご10箱",
        )

        assert result["success"] is False
        assert "not configured" in result["error"]


# ── 3. GraphEmailService のテスト ─────────────────────────────────────


class TestGraphEmailService:
    """GraphEmailService の Graph API 呼び出しテスト."""

    @pytest.mark.asyncio
    async def test_send_email_calls_graph_api(self):
        from src.connectors.adapters.graph_email_service import GraphEmailService

        config = ConnectorConfig(
            type="microsoft_graph",
            extra={
                "tenant_id": "test-tenant",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "sender_email": "orders@test.com",
            },
        )
        service = GraphEmailService(config)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            token_resp = MagicMock()
            token_resp.status_code = 200
            token_resp.json.return_value = {"access_token": "fake-token"}

            send_resp = MagicMock()
            send_resp.status_code = 202

            mock_client.post.side_effect = [token_resp, send_resp]

            result = await service.send_email(
                tenant_id="T-TEST",
                to_address="customer@example.com",
                subject="テスト件名",
                body_html="<p>テスト本文</p>",
            )

            assert result["success"] is True
            assert mock_client.post.call_count == 2

            send_call = mock_client.post.call_args_list[1]
            assert "sendMail" in send_call.args[0]
            assert send_call.kwargs["json"]["message"]["subject"] == "テスト件名"

    @pytest.mark.asyncio
    async def test_send_email_token_failure(self):
        from src.connectors.adapters.graph_email_service import GraphEmailService

        config = ConnectorConfig(
            type="microsoft_graph",
            extra={
                "tenant_id": "test-tenant",
                "client_id": "bad-client",
                "client_secret": "bad-secret",
                "sender_email": "orders@test.com",
            },
        )
        service = GraphEmailService(config)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            token_resp = MagicMock()
            token_resp.status_code = 401
            token_resp.text = "Invalid credentials"
            mock_client.post.return_value = token_resp

            result = await service.send_email(
                tenant_id="T-TEST",
                to_address="customer@example.com",
                subject="テスト",
                body_html="<p>テスト</p>",
            )

            assert result["success"] is False
            assert "token" in result["error"].lower() or "401" in result["error"]
