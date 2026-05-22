from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.orchestrator import (
    FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS,
    OrderOrchestrator,
    _build_draft_from_intake,
    _enforce_response_policy,
    _format_memory_context,
    _inventory_requires_operator_review,
    _is_affirmative_reply,
    _is_inventory_inquiry,
    _parse_order_items,
)
from src.connectors.interfaces.inventory_service import InventoryStatus
from src.models.message_history import MessageHistory
from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone


def _make_orchestrator(mock_tenant_ctx) -> OrderOrchestrator:
    return OrderOrchestrator(
        tenant_ctx=mock_tenant_ctx,
        azure_openai_endpoint="https://test.openai.azure.com/",
        azure_openai_key="test-key",
    )


class TestParseOrderItems:
    def test_single_item(self):
        items = _parse_order_items("りんご5箱")
        assert len(items) == 1
        assert items[0]["raw_name"] == "りんご"
        assert items[0]["quantity"] == 5.0
        assert items[0]["unit"] == "箱"

    def test_multiple_items_comma(self):
        items = _parse_order_items("りんご10箱、バナナ20kg")
        assert len(items) == 2
        assert items[0]["raw_name"] == "りんご"
        assert items[1]["raw_name"] == "バナナ"

    def test_multiple_items_with_to(self):
        items = _parse_order_items("りんご5箱とバナナ10kg")
        assert len(items) == 2

    def test_no_unit(self):
        items = _parse_order_items("りんご5")
        assert len(items) == 1
        assert items[0]["unit"] is None

    def test_decimal_quantity(self):
        items = _parse_order_items("バナナ2.5kg")
        assert len(items) == 1
        assert items[0]["quantity"] == 2.5

    def test_empty_message(self):
        assert _parse_order_items("") == []

    def test_no_quantity(self):
        assert _parse_order_items("お願いします") == []


class TestBuildDraftFromIntake:
    def test_valid_draft(self):
        intake = {
            "customer_id": "C-001",
            "customer_name": "テスト社",
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 5,
                    "unit": "箱",
                }
            ],
        }
        draft = _build_draft_from_intake(intake)
        assert draft is not None
        assert draft["customer_id"] == "C-001"
        assert len(draft["items"]) == 1

    def test_missing_customer_id(self):
        assert _build_draft_from_intake({"items": [{"product_id": "P-001"}]}) is None

    def test_missing_items(self):
        assert _build_draft_from_intake({"customer_id": "C-001"}) is None

    def test_empty_items(self):
        assert _build_draft_from_intake({"customer_id": "C-001", "items": []}) is None


class TestExtractJson:
    def setup_method(self):
        self._orch = OrderOrchestrator.__new__(OrderOrchestrator)

    def test_json_in_code_block(self):
        text = '```json\n{"items": [1, 2]}\n```'
        assert self._orch._extract_json(text) == {"items": [1, 2]}

    def test_raw_json(self):
        text = 'Here is the result: {"ok": true} end'
        assert self._orch._extract_json(text) == {"ok": True}

    def test_no_json(self):
        assert self._orch._extract_json("no json here") is None

    def test_invalid_json(self):
        assert self._orch._extract_json("{broken: json}") is None


class TestInventoryReview:
    def test_all_reserved_is_accepted(self):
        assert not _inventory_requires_operator_review({"all_reserved": True, "items": [{"available": True}]})

    def test_all_available_false_requires_review(self):
        assert _inventory_requires_operator_review({"all_available": False})

    def test_item_reserve_failure_requires_review(self):
        assert _inventory_requires_operator_review({"items": [{"product_id": "P-001", "reserved": False}]})

    def test_alternatives_require_review(self):
        assert _inventory_requires_operator_review({"alternatives": [{"product_id": "P-ALT"}]})


class TestInventoryInquiry:
    def test_detects_inventory_inquiry(self):
        assert _is_inventory_inquiry("りんごの在庫ありますか") is True
        assert _is_inventory_inquiry("りんご10箱お願いします") is False
        assert _is_inventory_inquiry("在庫あればりんご10箱ください") is False

    @pytest.mark.asyncio
    async def test_phone_inventory_inquiry_checks_without_order_or_reservation(self, mock_tenant_ctx, sample_product):
        orch = _make_orchestrator(mock_tenant_ctx)

        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.list_all.return_value = [sample_product]
        product_master.fuzzy_match.return_value = sample_product

        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id=sample_product.id,
            product_name=sample_product.name,
            available_qty=12,
            unit="箱",
            is_sufficient=True,
        )

        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
        ):
            result = await orch.process_order_message(
                message="りんご10箱の在庫ありますか",
                line_user_id="+81312345678",
                source=OrderSource.PHONE,
            )

        assert result["intent"] == "inventory_inquiry"
        assert "12箱" in result["response"]
        assert "10箱" in result["response"]
        inventory.check.assert_awaited_once_with("T-TEST", sample_product.id, 10.0)
        inventory.reserve.assert_not_called()
        order_repo.save.assert_not_called()
        mock_invoke.assert_not_called()


class TestResponsePolicy:
    def test_allows_confirmation_phrase_for_accepted_order(self):
        response = "ご注文承りました。りんご1個で確定しました。"

        assert _enforce_response_policy(response, needs_confirmation=False, inventory_needs_review=False) == response

    def test_replaces_confirmation_phrase_when_user_confirmation_needed(self):
        response = _enforce_response_policy(
            "ご注文承りました。りんご150kgで確定しました。",
            needs_confirmation=True,
            inventory_needs_review=False,
        )

        normalized = response.replace(" ", "")
        assert "確認が必要" in response
        assert all(pattern not in normalized for pattern in FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS)

    def test_replaces_confirmation_phrase_when_inventory_requires_review(self):
        response = _enforce_response_policy(
            "在庫不足ですが、ご注文承りました。",
            needs_confirmation=True,
            inventory_needs_review=True,
        )

        normalized = response.replace(" ", "")
        assert "担当者が確認" in response
        assert all(pattern not in normalized for pattern in FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS)

    def test_keeps_safe_review_response(self):
        response = "在庫状況を確認中です。担当者が確認して折り返します。"

        assert _enforce_response_policy(response, needs_confirmation=True, inventory_needs_review=True) == response


class TestMemoryContext:
    def test_format_memory_context(self):
        history = [
            MessageHistory(
                id="msg-1",
                tenant_id="T-TEST",
                session_id="sess-1",
                channel="line",
                channel_user_id="U123",
                role="user",
                text="りんご150kg",
            ),
            MessageHistory(
                id="msg-2",
                tenant_id="T-TEST",
                session_id="sess-1",
                channel="line",
                channel_user_id="U123",
                role="assistant",
                text="通常より多いですが、よろしいですか？",
            ),
        ]

        context = _format_memory_context(history, {"customer_id": "C-001", "items": []})

        assert "会話履歴" in context
        assert "顧客: りんご150kg" in context
        assert "確認待ち注文ドラフト" in context

    def test_affirmative_reply(self):
        assert _is_affirmative_reply("OK") is True
        assert _is_affirmative_reply("それでお願いします") is True
        assert _is_affirmative_reply("りんごを15kgに変更") is False


class TestProcessOrderMessageSendsOnce:
    """Verify that process_order_message sends exactly one LINE message — no more, no less."""

    @pytest.mark.asyncio
    async def test_sends_once_on_intake_fallback(self, mock_tenant_ctx):
        """When intake returns no parseable draft, orchestrator sends one message."""
        orch = _make_orchestrator(mock_tenant_ctx)

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            mock_invoke.return_value = "すみません、理解できませんでした。"

            result = await orch.process_order_message(
                message="キャビアとりんご1個お願い。",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

            assert mock_send.call_count == 1
            assert result["response"] != ""

    @pytest.mark.asyncio
    async def test_sends_once_on_successful_order(self, mock_tenant_ctx):
        """When full chain succeeds, orchestrator sends exactly one message."""
        orch = _make_orchestrator(mock_tenant_ctx)

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [
                    {
                        "product_id": "P-001",
                        "product_name": "りんご",
                        "quantity": 1,
                        "unit": "個",
                    }
                ],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            elif call_count == 2:
                return '```json\n{"anomalies": [], "confirmation_needed": false}\n```'
            elif call_count == 3:
                return '```json\n{"all_reserved": true}\n```'
            else:
                return "ご注文承りました。りんご1個ですね。"

        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders = []

        async def save_order(order):
            saved_orders.append(order)
            return "ORD-001"

        order_repo.save = AsyncMock(side_effect=save_order)

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="りんご1個お願い",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                session_id="sess-order",
            )

            assert mock_send.call_count == 1
            assert result.get("order_id") == "ORD-001"
            assert saved_orders[0].session_id == "sess-order"

    @pytest.mark.asyncio
    async def test_sends_once_on_confirmation_needed(self, mock_tenant_ctx):
        """When confirmation is needed, still sends exactly one message."""
        orch = _make_orchestrator(mock_tenant_ctx)

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [
                    {
                        "product_id": "P-001",
                        "product_name": "りんご",
                        "quantity": 150,
                        "unit": "kg",
                    }
                ],
                "needs_confirmation": True,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            elif call_count == 2:
                return '```json\n{"anomalies": [{"type": "quantity"}], "confirmation_needed": true}\n```'
            else:
                return "りんご150kgは通常より多いですが、よろしいですか？"

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="りんご150kg",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

            assert mock_send.call_count == 1
            assert result.get("session_status") == "awaiting_reply"
            assert result.get("pending_order_draft")
            assert "order_id" not in result

    @pytest.mark.asyncio
    async def test_affirmative_reply_creates_order_from_pending_draft(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders = []

        async def save_order(order):
            saved_orders.append(order)
            return "ORD-OK"

        order_repo.save = AsyncMock(side_effect=save_order)

        pending_draft = {
            "customer_id": "C-001",
            "customer_name": "テスト社",
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 1,
                    "unit": "個",
                }
            ],
        }

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            mock_invoke.return_value = "ご注文を確定しました。"

            result = await orch.process_order_message(
                message="OK",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                pending_order_draft=pending_draft,
                session_id="sess-confirm",
            )

            assert result["order_id"] == "ORD-OK"
            assert mock_send.call_count == 1
            assert saved_orders[0].session_id == "sess-confirm"

    @pytest.mark.asyncio
    async def test_inventory_shortage_saves_review_order_not_confirmed_order(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders = []

        async def save_order(order):
            saved_orders.append(order)
            return "ORD-REVIEW"

        order_repo.save = AsyncMock(side_effect=save_order)

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 10, "unit": "箱"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            if call_count == 2:
                return '```json\n{"anomalies": [], "confirmation_needed": false}\n```'
            if call_count == 3:
                return '```json\n{"all_available": false, "items": [{"product_id": "P-001", "available": false}], "message": "在庫不足です"}\n```'
            assert "受注確定していません" in message
            return "在庫確認が必要なため、担当者が確認いたします。"

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="りんご10箱",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                session_id="sess-review",
            )

            assert result["review_order_id"] == "ORD-REVIEW"
            assert "order_id" not in result
            assert result["session_status"] == "awaiting_reply"
            assert saved_orders[0].status == OrderStatus.NEEDS_REVIEW
            assert saved_orders[0].remarks == "在庫不足です"
            assert saved_orders[0].session_id == "sess-review"
            assert mock_send.call_count == 1

    @pytest.mark.asyncio
    async def test_inventory_shortage_sanitizes_unsafe_agent_reply(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-REVIEW")

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 10, "unit": "箱"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            if call_count == 2:
                return '```json\n{"anomalies": [], "confirmation_needed": false}\n```'
            if call_count == 3:
                return '```json\n{"all_reserved": false, "message": "在庫引当できません"}\n```'
            return "ご注文承りました。りんご10箱で確定しました。"

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
        ):
            result = await orch.process_order_message(
                message="りんご10箱",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

            normalized = result["response"].replace(" ", "")
            assert result["review_order_id"] == "ORD-REVIEW"
            assert all(pattern not in normalized for pattern in FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS)
            assert "担当者が確認" in result["response"]


class TestEndToEndMessageFlow:
    """Integration-level test: handler + orchestrator together send exactly one message."""

    @pytest.mark.asyncio
    async def test_handler_plus_orchestrator_sends_once(self, mock_tenant_ctx):
        """The full LINE webhook flow must result in exactly one LINE API call."""
        from src.services.line_handler import LineWebhookHandler

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [
                    {
                        "product_id": "P-001",
                        "product_name": "りんご",
                        "quantity": 1,
                        "unit": "個",
                    }
                ],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            elif call_count == 2:
                return '```json\n{"anomalies": [], "confirmation_needed": false}\n```'
            elif call_count == 3:
                return '```json\n{"all_reserved": true}\n```'
            else:
                return "りんご1個、承りました。"

        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-001")

        # Track all LINE API calls across both handler and orchestrator
        line_api_calls: list[str] = []

        async def track_push(user_id, message):
            line_api_calls.append(f"push:{user_id}:{message[:20]}")
            return True

        orch = handler._orchestrator

        # Mock the agent invocation but let the real orchestrator flow run
        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_orch_send,
            patch.object(handler, "_send_line_push", side_effect=track_push) as mock_handler_push,
        ):
            await handler._process_message("U123", "りんご1個", "tok-1")

            # Orchestrator sends once
            assert mock_orch_send.call_count == 1
            # Handler does NOT send (no duplicate)
            assert mock_handler_push.call_count == 0
            assert len(line_api_calls) == 0

    @pytest.mark.asyncio
    async def test_handler_sends_fallback_on_error(self, mock_tenant_ctx):
        """On orchestrator exception, handler sends exactly one fallback message."""
        from src.services.line_handler import LineWebhookHandler

        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s

        handler = LineWebhookHandler(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

        with (
            patch.object(
                handler._orchestrator,
                "process_order_message",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM down"),
            ),
            patch.object(handler, "_send_line_push", new_callable=AsyncMock) as mock_push,
        ):
            mock_push.return_value = True

            result = await handler._process_message("U123", "りんご1個", "tok-1")

            assert result["error"] == "agent_processing_failed"
            assert mock_push.call_count == 1
            assert "担当者が確認" in mock_push.call_args[0][1]


class TestLearningIntegration:
    """Orchestrator が受注確定時に Learning Service をバックグラウンド起動する。"""

    def _make_order(self) -> Order:
        return Order(
            uid="ORD-LEARN-001",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="テスト社",
            order_date=date.today(),
            source=OrderSource.LINE,
            items=[
                OrderItem(
                    product_id="P-001",
                    product_name="りんご",
                    quantity=5,
                    unit="箱",
                    temperature_zone=TemperatureZone.CHILLED,
                ),
                OrderItem(
                    product_id="P-002",
                    product_name="バナナ",
                    quantity=10,
                    unit="kg",
                    temperature_zone=TemperatureZone.AMBIENT,
                ),
            ],
            status=OrderStatus.ACCEPTED,
        )

    @pytest.mark.asyncio
    async def test_run_learning_calls_record_pattern_and_update_profile(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order = self._make_order()

        with patch("src.services.learning_service.LearningService", autospec=True) as MockLS:
            mock_ls = AsyncMock()
            MockLS.return_value = mock_ls

            await orch._run_learning(order, "りんご5箱とバナナ10kg")

            mock_ls.record_pattern.assert_awaited_once()
            call_kwargs = mock_ls.record_pattern.call_args[1]
            assert call_kwargs["customer_id"] == "C-001"
            assert call_kwargs["input_expression"] == "りんご5箱とバナナ10kg"
            assert len(call_kwargs["resolved_items"]) == 2

            assert mock_ls.update_customer_profile.await_count == 2

    @pytest.mark.asyncio
    async def test_run_learning_exception_does_not_propagate(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order = self._make_order()

        with patch("src.services.learning_service.LearningService", side_effect=RuntimeError("DB down")):
            await orch._run_learning(order, "りんご5箱")

    @pytest.mark.asyncio
    async def test_affirmative_reply_triggers_learning_task(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-LEARN")

        pending_draft = {
            "customer_id": "C-001",
            "customer_name": "テスト社",
            "items": [
                {"product_id": "P-001", "product_name": "りんご", "quantity": 5, "unit": "箱"},
            ],
        }

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock, return_value="ご注文を確定しました。"),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch.object(orch, "_run_learning", new_callable=AsyncMock) as mock_learn,
        ):
            await orch.process_order_message(
                message="OK",
                line_user_id="U123",
                source=OrderSource.LINE,
                pending_order_draft=pending_draft,
            )

            mock_learn.assert_called_once()
            args = mock_learn.call_args[0]
            assert args[0].id == "ORD-LEARN"
            assert args[1] == "OK"

    @pytest.mark.asyncio
    async def test_normal_flow_triggers_learning_task(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-NORMAL")

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 1, "unit": "個"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            elif call_count == 2:
                return '```json\n{"anomalies": [], "confirmation_needed": false}\n```'
            elif call_count == 3:
                return '```json\n{"all_reserved": true}\n```'
            else:
                return "りんご1個、承りました。"

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch.object(orch, "_run_learning", new_callable=AsyncMock) as mock_learn,
        ):
            await orch.process_order_message(
                message="りんご1個",
                line_user_id="U123",
                source=OrderSource.LINE,
            )

            mock_learn.assert_called_once()
            args = mock_learn.call_args[0]
            assert args[0].id == "ORD-NORMAL"
            assert args[1] == "りんご1個"

    @pytest.mark.asyncio
    async def test_needs_review_does_not_trigger_learning(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-REVIEW")

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "テスト社",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 10, "unit": "箱"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"```json\n{intake_json}\n```"
            if call_count == 2:
                return '```json\n{"anomalies": [], "confirmation_needed": false}\n```'
            if call_count == 3:
                return '```json\n{"all_available": false, "items": [{"product_id": "P-001", "available": false}]}\n```'
            return "担当者が確認いたします。"

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch.object(orch, "_run_learning", new_callable=AsyncMock) as mock_learn,
        ):
            await orch.process_order_message(
                message="りんご10箱",
                line_user_id="U123",
                source=OrderSource.LINE,
            )

            mock_learn.assert_not_called()
