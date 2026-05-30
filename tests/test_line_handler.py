from __future__ import annotations

from datetime import date
import time
from unittest.mock import ANY, AsyncMock, patch

import pytest

from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.services.line_handler import LineWebhookHandler, _EventDedup, _pick_current_order


class TestEventDedup:
    @pytest.mark.asyncio
    async def test_first_event_not_duplicate(self):
        dedup = _EventDedup(ttl=60)
        assert await dedup.is_duplicate("evt-001") is False

    @pytest.mark.asyncio
    async def test_second_event_is_duplicate(self):
        dedup = _EventDedup(ttl=60)
        await dedup.is_duplicate("evt-001")
        assert await dedup.is_duplicate("evt-001") is True

    @pytest.mark.asyncio
    async def test_different_events_not_duplicate(self):
        dedup = _EventDedup(ttl=60)
        await dedup.is_duplicate("evt-001")
        assert await dedup.is_duplicate("evt-002") is False

    @pytest.mark.asyncio
    async def test_expired_event_not_duplicate(self):
        dedup = _EventDedup(ttl=1)
        await dedup.is_duplicate("evt-001")
        time.sleep(1.1)
        assert await dedup.is_duplicate("evt-001") is False


class TestVerifySignature:
    def test_valid_signature(self, mock_tenant_ctx):
        import base64
        import hashlib
        import hmac

        secret = "test-secret"
        body = b'{"events":[]}'
        expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()

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

    def test_no_secret_configured_rejects(self, mock_tenant_ctx):
        """Fail-closed: when channel secret is missing, signature check must fail."""
        mock_tenant_ctx.config.line_channel_secret = None
        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )
        assert handler.verify_signature(b"body", "any") is False


class TestPickCurrentOrder:
    def test_skips_needs_review_orders_created_for_unavailable_items(self):
        review_order = Order(
            uid="ORD-REVIEW",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_date=date.today(),
            source=OrderSource.LINE,
            status=OrderStatus.NEEDS_REVIEW,
            items=[
                OrderItem(
                    product_id="P-001",
                    product_name="りんご",
                    quantity=10,
                    unit="箱",
                    temperature_zone=TemperatureZone.CHILLED,
                )
            ],
        )
        accepted_order = Order(
            uid="ORD-ACCEPTED",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_date=date.today(),
            source=OrderSource.LINE,
            status=OrderStatus.ACCEPTED,
            items=[
                OrderItem(
                    product_id="P-002",
                    product_name="バナナ",
                    quantity=1,
                    unit="kg",
                    temperature_zone=TemperatureZone.AMBIENT,
                )
            ],
        )

        assert _pick_current_order([review_order]) is None
        assert _pick_current_order([review_order, accepted_order]).id == "ORD-ACCEPTED"

    def test_skips_shipping_orders_so_new_orders_are_not_blocked(self):
        shipping_order = Order(
            uid="ORD-SHIPPING",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_date=date.today(),
            source=OrderSource.LINE,
            status=OrderStatus.SHIPPING,
            items=[
                OrderItem(
                    product_id="P-001",
                    product_name="りんご",
                    quantity=5,
                    unit="箱",
                    temperature_zone=TemperatureZone.CHILLED,
                )
            ],
        )
        assert _pick_current_order([shipping_order]) is None


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
                {
                    "type": "message",
                    "message": {"type": "image"},
                    "source": {"userId": "U123"},
                },
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
            mock_proc.assert_called_once_with(
                "U123",
                "りんご5箱",
                "token-1",
                message_id=None,
                webhook_event_id="evt-unique-1",
                received_at=ANY,
            )

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

        async def track_calls(user_id, text, reply_token, **kwargs):
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
            mock_orch.process_order_message = AsyncMock(return_value={"response": "ご注文承りました"})
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                await handler._process_message("U123", "テスト", None)

                session_repo.create_session.assert_called_once()
                history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")
                history_repo.list_recent_messages.assert_called_once_with("T-TEST", "line", "U123", 20)
                assert history_repo.create_message.call_count == 2
                # Handler must NOT send — orchestrator already sent the message
                mock_push.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_send_on_success(self, mock_tenant_ctx):
        """Regression: handler must not re-send the message that orchestrator already sent."""
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
                return_value={"response": "確認しました", "order_id": "ORD-001"}
            )
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                result = await handler._process_message("U123", "りんご5箱", "token-1")

                mock_push.assert_not_called()
                assert result["result"]["response"] == "確認しました"

    @pytest.mark.asyncio
    async def test_passes_conversation_history_and_pending_draft(self, mock_tenant_ctx):
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")
        history_repo.list_recent_messages.return_value = []

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(
                return_value={
                    "response": "数量をご確認ください",
                    "session_status": "awaiting_reply",
                    "pending_order_draft": {"customer_id": "C-001", "items": []},
                }
            )

            await handler._process_message("U123", "りんご150kg", "token-1", webhook_event_id="evt-history-1")

            mock_orch.process_order_message.assert_called_once()
            _, kwargs = mock_orch.process_order_message.call_args
            assert kwargs["conversation_history"] == []
            assert kwargs["pending_order_draft"] is None
            assert session_repo.update_session.call_count == 1
            updated_session = session_repo.update_session.call_args.args[0]
            assert updated_session.status == "awaiting_reply"
            assert updated_session.pending_order_draft == {
                "customer_id": "C-001",
                "items": [],
            }

    @pytest.mark.asyncio
    async def test_passes_current_order_to_orchestrator_and_persists_snapshot(self, mock_tenant_ctx, sample_customer):
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.find_by_line_user_id.return_value = sample_customer
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        current_order = Order(
            uid="ORD-CURRENT",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="株式会社テスト",
            order_date=date.today(),
            delivery_date=None,
            source=OrderSource.LINE,
            status=OrderStatus.ACCEPTED,
            items=[
                OrderItem(
                    product_id="P-001",
                    product_name="りんご",
                    quantity=2,
                    unit="箱",
                    temperature_zone=TemperatureZone.CHILLED,
                )
            ],
        )
        order_repo.list_by_customer.return_value = [current_order]

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(return_value={"response": "確認しました"})
            await handler._process_message("U123", "白菜を追加で", "token-1")

            _, kwargs = mock_orch.process_order_message.call_args
            assert kwargs["current_order"].id == "ORD-CURRENT"
            updated_session = session_repo.create_session.call_args.args[0]
            assert updated_session.current_order_id == "ORD-CURRENT"

    @pytest.mark.asyncio
    async def test_history_failure_does_not_block_reply(self, mock_tenant_ctx):
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")
        history_repo.list_recent_messages.side_effect = RuntimeError("container missing")
        history_repo.create_message.side_effect = RuntimeError("container missing")

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(return_value={"response": "ご注文承りました"})
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                result = await handler._process_message("U123", "りんご5箱", "token-1")

                mock_orch.process_order_message.assert_called_once()
                _, kwargs = mock_orch.process_order_message.call_args
                assert kwargs["conversation_history"] == []
                assert result["result"]["response"] == "ご注文承りました"
                mock_push.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_send_empty_response(self, mock_tenant_ctx):
        """Even when response is empty, handler should not attempt to send."""
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(return_value={"response": ""})
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                await handler._process_message("U123", "テスト", None)
                mock_push.assert_not_called()

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
                mock_push.assert_called_once_with("U123", "ご注文を受け付けました。担当者が確認いたします。")

    @pytest.mark.asyncio
    async def test_fallback_sends_exactly_once(self, mock_tenant_ctx):
        """Error fallback must send exactly one message, not zero or two."""
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with patch.object(handler, "_orchestrator") as mock_orch:
            mock_orch.process_order_message = AsyncMock(side_effect=Exception("boom"))
            with patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push:
                mock_push.return_value = True
                await handler._process_message("U123", "りんご", None)
                assert mock_push.call_count == 1
