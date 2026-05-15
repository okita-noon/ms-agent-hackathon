from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.session import OrderSession
from src.services.line_handler import LineWebhookHandler, _EventDedup


class TestEventDedup:
    def test_first_event_not_duplicate(self):
        dedup = _EventDedup(ttl=60)
        assert dedup.is_duplicate("evt-001") is False

    def test_second_event_is_duplicate(self):
        dedup = _EventDedup(ttl=60)
        dedup.is_duplicate("evt-001")
        assert dedup.is_duplicate("evt-001") is True

    def test_different_events_not_duplicate(self):
        dedup = _EventDedup(ttl=60)
        dedup.is_duplicate("evt-001")
        assert dedup.is_duplicate("evt-002") is False

    def test_expired_event_not_duplicate(self):
        dedup = _EventDedup(ttl=1)
        dedup.is_duplicate("evt-001")
        time.sleep(1.1)
        assert dedup.is_duplicate("evt-001") is False


class TestVerifySignature:
    def test_valid_signature(self, mock_tenant_ctx):
        import base64
        import hashlib
        import hmac

        secret = "test-secret"
        body = b'{"events":[]}'
        expected = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        assert handler.verify_signature(body, expected) is True

    def test_invalid_signature(self, mock_tenant_ctx):
        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        assert handler.verify_signature(b"body", "invalid-sig") is False

    def test_no_secret_configured(self, mock_tenant_ctx):
        mock_tenant_ctx.config.line_channel_secret = None
        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        assert handler.verify_signature(b"body", "any") is True


class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_filters_non_text_messages(self, mock_tenant_ctx):
        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        body = {
            "events": [
                {"type": "follow", "source": {"userId": "U123"}},
                {"type": "message", "message": {"type": "image"}, "source": {"userId": "U123"}},
            ]
        }

        with patch.object(handler, "_process_message", new_callable=AsyncMock) as mock_proc:
            results = await handler.handle_webhook(body)
            mock_proc.assert_not_called()
            assert results == []

    @pytest.mark.asyncio
    async def test_processes_text_messages(self, mock_tenant_ctx):
        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        body = {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "text": "りんご5箱"},
                    "source": {"userId": "U123"},
                    "replyToken": "token-1",
                    "timestamp": 1000,
                    "webhookEventId": "evt-unique-1",
                },
            ]
        }

        with patch.object(handler, "_process_message", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = {"status": "ok"}
            results = await handler.handle_webhook(body)
            assert len(results) == 1
            mock_proc.assert_called_once_with("U123", "りんご5箱", "token-1")

    @pytest.mark.asyncio
    async def test_sorts_by_timestamp(self, mock_tenant_ctx):
        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        body = {
            "events": [
                {
                    "type": "message",
                    "message": {"type": "text", "text": "second"},
                    "source": {"userId": "U123"},
                    "timestamp": 2000,
                    "webhookEventId": "evt-sort-2",
                },
                {
                    "type": "message",
                    "message": {"type": "text", "text": "first"},
                    "source": {"userId": "U123"},
                    "timestamp": 1000,
                    "webhookEventId": "evt-sort-1",
                },
            ]
        }

        call_order = []

        async def track_calls(user_id, text, reply_token):
            call_order.append(text)
            return {"status": "ok"}

        with patch.object(handler, "_process_message", side_effect=track_calls):
            await handler.handle_webhook(body)
            assert call_order == ["first", "second"]


class TestProcessMessage:
    @pytest.mark.asyncio
    async def test_creates_session_for_new_user(self, mock_tenant_ctx):
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(
                return_value={"response": "ご注文承りました"}
            )
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                mock_push.return_value = True
                result = await handler._process_message("U123", "テスト", None)

                session_repo.create_session.assert_called_once()
                mock_push.assert_called_once_with("U123", "ご注文承りました")

    @pytest.mark.asyncio
    async def test_fallback_on_orchestrator_error(self, mock_tenant_ctx):
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(side_effect=RuntimeError("LLM error"))
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                mock_push.return_value = True
                result = await handler._process_message("U123", "テスト", None)

                assert result["error"] == "agent_processing_failed"
                mock_push.assert_called_once_with(
                    "U123", "ご注文を受け付けました。担当者が確認いたします。"
                )
