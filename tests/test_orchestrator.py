from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.utils.business_date import today_jst

from src.agents.orchestrator import (
    FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS,
    _apply_known_customer_to_intake,
    OrderOrchestrator,
    _check_draft_inventory,
    _build_draft_from_intake,
    _classify_additional_order,
    _enforce_response_policy,
    _extract_quantity_only_reply,
    _format_open_orders_summary,
    _format_memory_context,
    _intake_draft_reflects_message,
    _inventory_requires_operator_review,
    _is_affirmative_reply,
    _is_current_order_inquiry,
    _is_full_order_cancel,
    _is_inventory_inquiry,
    _is_negative_reply,
    _parse_order_items,
    _resolve_line_action_type,
)
from src.connectors.interfaces.inventory_service import InventoryStatus
from src.models.inbound import InboundMessage
from src.models.intelligence import OrderPattern, ResolvedItem
from src.models.message_history import MessageHistory
from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.models.product import Product, UnitType
from src.models.session import OrderSession
from src.services.intent_understanding import OrderIntent


def _make_orchestrator(mock_tenant_ctx) -> OrderOrchestrator:
    return OrderOrchestrator(
        tenant_ctx=mock_tenant_ctx,
        azure_openai_endpoint="https://test.openai.azure.com/",
        azure_openai_key="test-key",
    )


def _make_current_order(status: OrderStatus = OrderStatus.ACCEPTED) -> Order:
    today = today_jst()
    return Order(
        uid="ORD-CURRENT",
        tenant_id="T-TEST",
        customer_id="C-001",
        customer_name="テスト社",
        order_date=today,
        delivery_date=today,
        source=OrderSource.LINE,
        status=status,
        items=[
            OrderItem(
                product_id="P-001",
                product_name="りんご",
                quantity=1,
                unit="箱",
                temperature_zone=TemperatureZone.CHILLED,
            )
        ],
    )


class TestParseOrderItems:
    def test_single_item(self):
        items = _parse_order_items("りんご5箱")
        assert len(items) == 1
        assert items[0]["raw_name"] == "りんご"
        assert items[0]["quantity"] == 5.0
        assert items[0]["unit"] == "箱"

    def test_normalizes_japanese_quantity_and_kilo(self):
        items = _parse_order_items("もも一キロ")
        assert len(items) == 1
        assert items[0]["raw_name"] == "もも"
        assert items[0]["quantity"] == 1.0
        assert items[0]["unit"] == "kg"

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

    def test_strips_particle_wo(self):
        items = _parse_order_items("いちじくを300箱お願いします！")
        assert len(items) == 1
        assert items[0]["raw_name"] == "いちじく"
        assert items[0]["quantity"] == 300.0
        assert items[0]["unit"] == "箱"

    def test_keeps_non_wo_particles(self):
        items = _parse_order_items("りんごに10箱")
        assert len(items) == 1
        assert items[0]["raw_name"] == "りんごに"


class TestIntakeDraftReflectsMessage:
    def test_matching_items(self):
        draft = {"items": [{"product_name": "いちじく", "quantity": 300, "unit": "箱"}]}
        assert _intake_draft_reflects_message(draft, "いちじくを300箱お願いします！") is True

    def test_missing_items(self):
        draft = {"items": [{"product_name": "梨", "quantity": 10, "unit": "個"}]}
        assert _intake_draft_reflects_message(draft, "いちじくを300箱お願いします！") is False

    def test_partial_match(self):
        draft = {
            "items": [
                {"product_name": "りんご", "quantity": 10, "unit": "箱"},
                {"product_name": "バナナ", "quantity": 20, "unit": "kg"},
            ]
        }
        assert _intake_draft_reflects_message(draft, "りんご10箱、バナナ20kg") is True

    def test_no_parseable_items_in_message(self):
        draft = {"items": [{"product_name": "梨", "quantity": 10, "unit": "個"}]}
        assert _intake_draft_reflects_message(draft, "お願いします") is True

    def test_empty_draft_items(self):
        draft = {"items": []}
        assert _intake_draft_reflects_message(draft, "りんご10箱") is False


class TestBuildDraftFromIntake:
    def test_valid_draft(self):
        intake = {
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
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

    def test_defaults_delivery_date_to_jst_business_date(self):
        intake = {
            "customer_id": "C-001",
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 5,
                    "unit": "箱",
                }
            ],
        }

        with patch("src.agents.orchestrator.today_jst", return_value=date(2026, 5, 26)):
            draft = _build_draft_from_intake(intake)

        assert draft is not None
        assert draft["delivery_date"] == date(2026, 5, 26)


class TestApplyKnownCustomerToIntake:
    def test_fills_missing_customer_fields_from_known_context(self):
        draft = _apply_known_customer_to_intake(
            {"items": [{"product_id": "P-001"}]},
            known_customer_id="C-001",
            known_customer_name="ビストロ青葉",
        )

        assert draft["customer_id"] == "C-001"
        assert draft["customer_name"] == "ビストロ青葉"

    def test_keeps_agent_customer_fields_when_present(self):
        draft = _apply_known_customer_to_intake(
            {
                "customer_id": "C-999",
                "customer_name": "別顧客",
                "items": [{"product_id": "P-001"}],
            },
            known_customer_id="C-001",
            known_customer_name="ビストロ青葉",
        )

        assert draft["customer_id"] == "C-999"
        assert draft["customer_name"] == "別顧客"


class TestExtractQuantityOnlyReply:
    def test_accepts_nishite_suffix(self):
        assert _extract_quantity_only_reply("1000個にして。") == (1000.0, "個")

    def test_accepts_nishitekudasai_suffix(self):
        assert _extract_quantity_only_reply("やっぱり 12箱にしてください") == (12.0, "箱")


@pytest.mark.asyncio
async def test_check_draft_inventory_falls_back_when_status_name_unknown():
    inventory = AsyncMock()
    inventory.check.return_value = InventoryStatus(
        product_id="P-001",
        product_name="不明",
        available_qty=0.0,
        unit="箱",
        is_sufficient=False,
    )

    class DummyCtx:
        tenant_id = "T-001"

        def get_connector(self, name: str):
            assert name == "IInventoryService"
            return inventory

    draft = {
        "items": [
            {"product_id": "P-001", "product_name": "卵", "quantity": 1, "unit": "箱"},
        ]
    }
    checked = await _check_draft_inventory(DummyCtx(), draft)
    assert checked[0]["product_name"] == "卵"


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


class TestCurrentOrderInquiry:
    def test_match_current_order_keywords(self):
        assert _is_current_order_inquiry("今の注文は？")
        assert _is_current_order_inquiry("現在の注文状況を教えて")

    def test_not_match_general_order_message(self):
        assert not _is_current_order_inquiry("バナナ5kgお願いします")

    def test_format_open_orders_summary_group_by_delivery_date(self):
        orders = [
            Order(
                id="ORD-1",
                tenant_id="T-001",
                order_date=date(2026, 5, 26),
                delivery_date=date(2026, 5, 28),
                customer_id="C-001",
                customer_name="Test",
                source=OrderSource.LINE,
                status=OrderStatus.ACCEPTED,
                items=[
                    OrderItem(
                        product_id="P-001",
                        product_name="りんご",
                        quantity=2,
                        unit="箱",
                        temperature_zone=TemperatureZone.AMBIENT,
                    )
                ],
            ),
            Order(
                id="ORD-2",
                tenant_id="T-001",
                order_date=date(2026, 5, 26),
                delivery_date=date(2026, 5, 29),
                customer_id="C-001",
                customer_name="Test",
                source=OrderSource.LINE,
                status=OrderStatus.ACCEPTED,
                items=[
                    OrderItem(
                        product_id="P-002",
                        product_name="バナナ",
                        quantity=5,
                        unit="kg",
                        temperature_zone=TemperatureZone.AMBIENT,
                    )
                ],
            ),
        ]
        summary = _format_open_orders_summary(orders)
        assert "【5/28配送予定】" in summary
        assert "・りんご 2箱" in summary
        assert "【5/29配送予定】" in summary
        assert "・バナナ 5kg" in summary

    @pytest.mark.asyncio
    async def test_inquiry_returns_open_order_summary(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.list_by_customer.return_value = [
            Order(
                id="ORD-1",
                tenant_id="T-TEST",
                customer_id="C-001",
                customer_name="テスト社",
                order_date=date(2026, 5, 26),
                delivery_date=date(2026, 5, 28),
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
        ]

        with (
            patch("src.agents.orchestrator.today_jst", return_value=date(2026, 5, 26)),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="今の注文は？",
                line_user_id="WEB-C-001",
                reply_token="tok",
                source=OrderSource.LINE,
                known_customer_id="C-001",
            )

        assert "現在のご注文内容" in result["response"]
        assert "・りんご 2箱" in result["response"]
        mock_send.assert_awaited_once()

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


class TestLineCancelPhrases:
    @pytest.mark.parametrize(
        "message",
        [
            "全部キャンセルでお願いします",
            "全てキャンセルしてください",
            "すべてキャンセルで",
            "注文キャンセルお願いします",
            "さっきの注文キャンセルで",
            "キャンセルでお願いします",
            "前の注文をキャンセルしてください",
            "やっぱりやめます",
            "今の注文なしでお願いします",
            "全部なしでお願いします",
            "全キャンセルで",
        ],
    )
    def test_full_cancel_phrase_is_classified_without_llm(self, message):
        assert _is_full_order_cancel(message)
        assert _resolve_line_action_type(message, current_order=_make_current_order()) == "full_cancel"

    @pytest.mark.parametrize(
        "message",
        [
            "キャンセルでお願いします",
            "前の注文をキャンセルしてください",
            "やっぱりやめます",
            "今の注文なしでお願いします",
        ],
    )
    @pytest.mark.asyncio
    async def test_natural_full_cancel_phrase_updates_current_order_without_agent_call(self, mock_tenant_ctx, message):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.update_status = AsyncMock()
        current_order = _make_current_order()

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message=message,
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                current_order=current_order,
            )

        order_repo.update_status.assert_awaited_once_with("T-TEST", "ORD-CURRENT", OrderStatus.CANCELLED)
        mock_invoke.assert_not_called()
        mock_send.assert_awaited_once()
        assert result["current_order_cleared"] is True

    @pytest.mark.asyncio
    async def test_ambiguous_cancel_phrase_uses_llm_intent_for_current_order(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.update_status = AsyncMock()
        current_order = _make_current_order()

        with (
            patch.object(orch, "_make_orchestrator_agent", return_value=object()) as mock_make_agent,
            patch.object(
                orch,
                "_invoke_agent",
                new_callable=AsyncMock,
                return_value=(
                    '{"intent":"full_cancel","confidence":0.82,"requires_confirmation":false,"reason":"cancel"}',
                    0.1,
                ),
            ) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="やめとこうかな",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                current_order=current_order,
            )

        mock_make_agent.assert_called_once()
        prompt = mock_invoke.await_args.args[1]
        assert "intent JSON" in prompt
        assert "やめとこうかな" in prompt
        order_repo.update_status.assert_awaited_once_with("T-TEST", "ORD-CURRENT", OrderStatus.CANCELLED)
        mock_send.assert_awaited_once()
        assert result["current_order_cleared"] is True

    @pytest.mark.asyncio
    async def test_email_full_cancel_uses_current_order_from_session(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        current_order = _make_current_order()
        order_repo.find_by_id.return_value = current_order
        order_repo.update_status = AsyncMock()
        replies = []

        async def reply_callback(subject: str, body: str, reply_to_message_id: str | None) -> None:
            replies.append((subject, body, reply_to_message_id))

        inbound = InboundMessage(
            tenant_id="T-TEST",
            channel="email",
            channel_user_id="buyer@example.com",
            customer_id="C-001",
            customer_name="テスト社",
            subject="注文変更",
            text="前の注文をキャンセルしてください",
            received_at=datetime.now(),
            external_message_id="email-001",
            reply_to_message_id="email-root",
        )
        session = OrderSession(
            id="email-session",
            tenant_id="T-TEST",
            channel="email",
            channel_user_id="buyer@example.com",
            customer_id="C-001",
            current_order_id="ORD-CURRENT",
        )

        with patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke:
            result = await orch.process_email(inbound, session, reply_callback)

        order_repo.find_by_id.assert_awaited_once_with("T-TEST", "ORD-CURRENT")
        order_repo.update_status.assert_awaited_once_with("T-TEST", "ORD-CURRENT", OrderStatus.CANCELLED)
        mock_invoke.assert_not_called()
        assert result["current_order_cleared"] is True
        assert replies
        assert replies[0][0] == "Re: 注文変更 【受注No: ORD-CURRENT】"
        assert "キャンセルいたしました" in replies[0][1]


class TestMemoryOrderIntents:
    @pytest.mark.asyncio
    async def test_line_previous_order_creates_order_without_intake_llm(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.list_by_customer.return_value = [_make_current_order(status=OrderStatus.COMPLETED)]
        order_repo.save = AsyncMock(return_value="ORD-REPEAT")
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="りんご",
            available_qty=10,
            unit="箱",
            is_sufficient=True,
        )

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="前と同じでお願いします",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                known_customer_id="C-001",
                known_customer_name="テスト社",
            )

        mock_invoke.assert_not_called()
        order_repo.list_by_customer.assert_awaited_once_with("C-001", limit=10)
        order_repo.save.assert_awaited_once()
        inventory.check.assert_awaited_once_with("T-TEST", "P-001", 1.0)
        mock_send.assert_awaited_once()
        assert result["order_id"] == "ORD-REPEAT"
        assert result["current_order_id"] == "ORD-REPEAT"

    @pytest.mark.asyncio
    async def test_email_usual_order_creates_order_from_pattern(self, mock_tenant_ctx, sample_product):
        orch = _make_orchestrator(mock_tenant_ctx)
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = OrderPattern(
            tenant_id="T-TEST",
            customer_id="C-001",
            input_expression="いつもの",
            input_expression_normalized="いつもの",
            resolved_items=[ResolvedItem(product_id="P-001", product_name="りんご", qty=2, unit="箱")],
            confidence=0.95,
        )
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.get_by_id.return_value = sample_product
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-USUAL")
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="りんご",
            available_qty=10,
            unit="箱",
            is_sufficient=True,
        )
        replies = []

        async def reply_callback(subject: str, body: str, reply_to_message_id: str | None) -> None:
            replies.append((subject, body, reply_to_message_id))

        inbound = InboundMessage(
            tenant_id="T-TEST",
            channel="email",
            channel_user_id="buyer@example.com",
            customer_id="C-001",
            customer_name="テスト社",
            subject="注文",
            text="いつものお願いします",
            received_at=datetime.now(),
            external_message_id="email-002",
        )
        session = OrderSession(
            id="email-session",
            tenant_id="T-TEST",
            channel="email",
            channel_user_id="buyer@example.com",
            customer_id="C-001",
        )

        with patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke:
            result = await orch.process_email(inbound, session, reply_callback)

        mock_invoke.assert_not_called()
        store.find_pattern_exact.assert_awaited_once_with("T-TEST", "C-001", "いつものお願いします")
        order_repo.save.assert_awaited_once()
        assert result["order_id"] == "ORD-USUAL"
        assert replies[0][0] == "Re: 注文 【受注No: ORD-USUAL】"
        assert "受注No: ORD-USUAL" in replies[0][1]


class TestPhoneOrderUnified:
    """Phone orders now use process_order_message(source=PHONE) — same path as LINE."""

    @pytest.mark.asyncio
    async def test_phone_small_talk_returns_conversational_response(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        captured = []

        async def capture(text):
            captured.append(text)

        with patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = ("気持ちのよいお天気ですね。", 0.1)
            result = await orch.process_order_message(
                message="今日はいい天気ですね",
                line_user_id="+81312345678",
                source=OrderSource.PHONE,
                response_callback=capture,
                known_customer_id="C-001",
                known_customer_name="ビストロ青葉",
            )

        assert result.get("intent") == "small_talk"
        assert "ご注文がありましたら" in result["response"]
        assert result.get("order_saved") is not True
        inventory.check.assert_not_called()
        mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_phone_status_inquiry_resolves_customer_by_phone_number(self, mock_tenant_ctx, sample_customer):
        orch = _make_orchestrator(mock_tenant_ctx)
        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.find_by_identifier.return_value = sample_customer
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.list_by_customer.return_value = [_make_current_order()]
        captured = []

        async def capture(text):
            captured.append(text)

        result = await orch.process_order_message(
            message="今の注文は？",
            line_user_id="+81312345678",
            source=OrderSource.PHONE,
            response_callback=capture,
        )

        customer_repo.find_by_identifier.assert_awaited_once_with("T-TEST", "+81312345678")
        order_repo.list_by_customer.assert_awaited_once_with("C-001", limit=50)
        assert "現在のご注文内容" in result["response"]

    @pytest.mark.asyncio
    async def test_phone_usual_order_resolves_pattern_without_llm(self, mock_tenant_ctx, sample_product):
        orch = _make_orchestrator(mock_tenant_ctx)
        store = mock_tenant_ctx.get_connector("IOrderIntelligenceStore")
        store.find_pattern_exact.return_value = OrderPattern(
            tenant_id="T-TEST",
            customer_id="C-001",
            input_expression="いつもの",
            input_expression_normalized="いつもの",
            resolved_items=[ResolvedItem(product_id="P-001", product_name="りんご", qty=2, unit="箱")],
            confidence=0.95,
        )
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.get_by_id.return_value = sample_product
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="りんご",
            available_qty=10,
            unit="箱",
            is_sufficient=True,
        )
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-USUAL")
        captured = []

        async def capture(text):
            captured.append(text)

        result = await orch.process_order_message(
            message="いつものお願いします",
            line_user_id="+81312345678",
            source=OrderSource.PHONE,
            response_callback=capture,
            known_customer_id="C-001",
            known_customer_name="ビストロ青葉",
        )

        inventory.check.assert_awaited_once_with("T-TEST", "P-001", 2.0)
        assert result.get("order_saved") is True
        assert "りんご" in result["response"]
        assert "ORD-USUAL" not in result["response"]
        assert "受注No" not in result["response"]

    @pytest.mark.asyncio
    async def test_phone_previous_order_resolves_without_llm(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.list_by_customer.return_value = [_make_current_order(status=OrderStatus.COMPLETED)]
        order_repo.save = AsyncMock(return_value="ORD-PREV")
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="りんご",
            available_qty=10,
            unit="箱",
            is_sufficient=True,
        )
        captured = []

        async def capture(text):
            captured.append(text)

        result = await orch.process_order_message(
            message="前と同じでお願いします",
            line_user_id="+81312345678",
            source=OrderSource.PHONE,
            response_callback=capture,
            known_customer_id="C-001",
            known_customer_name="ビストロ青葉",
        )

        order_repo.list_by_customer.assert_awaited_once_with("C-001", limit=10)
        inventory.check.assert_awaited_once_with("T-TEST", "P-001", 1.0)
        assert result.get("order_saved") is True
        assert "りんご" in result["response"]
        assert "ORD-PREV" not in result["response"]
        assert "受注No" not in result["response"]


class TestKnownCustomerOrderSave:
    @pytest.mark.asyncio
    async def test_process_order_message_saves_when_known_customer_missing_from_agent_json(
        self, mock_tenant_ctx, sample_product
    ):
        orch = _make_orchestrator(mock_tenant_ctx)
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.list_all.return_value = [sample_product]
        inventory = mock_tenant_ctx.get_connector("IInventoryService")
        inventory.check.return_value = InventoryStatus(
            product_id="P-001",
            product_name="キウイ",
            available_qty=12,
            unit="個",
            is_sufficient=True,
        )
        inventory.reserve.return_value = True
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-KIWI")

        intake_draft = {
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "キウイ",
                    "quantity": 10,
                    "unit": "個",
                    "temperature_zone": "冷蔵",
                }
            ],
            "needs_confirmation": False,
        }

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            mock_invoke.side_effect = [
                (json.dumps(intake_draft, ensure_ascii=False), 0.5),
                (json.dumps({"confirmation_needed": False}, ensure_ascii=False), 0.2),
                ("キウイ10個を受注しました。", 0.2),
            ]
            result = await orch.process_order_message(
                message="キウイ10個",
                line_user_id="+81312345678",
                source=OrderSource.PHONE,
                known_customer_id="C-001",
                known_customer_name="ビストロ青葉",
            )

        saved_order = order_repo.save.call_args.args[0]
        assert saved_order.customer_id == "C-001"
        assert saved_order.customer_name == "ビストロ青葉"
        assert result["order_id"] == "ORD-KIWI"
        assert "ORD-KIWI" not in result["response"]
        assert "受注No" not in result["response"]
        inventory.check.assert_awaited_once_with("T-TEST", "P-001", 10.0)
        mock_send.assert_awaited_once()


class TestConversationBranching:
    @pytest.mark.asyncio
    async def test_email_small_talk_replies_without_order_agent(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        callback = AsyncMock()

        with patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = ("ご連絡ありがとうございます。", 0.1)
            result = await orch.process_order_message(
                message="お世話になっております。今日はいい天気ですね。",
                line_user_id="aoba@example.com",
                source=OrderSource.EMAIL,
                response_callback=callback,
                known_customer_id="C-001",
                known_customer_name="ビストロ青葉",
            )

        assert result["intent"] == "small_talk"
        assert "商品名と数量" in result["response"]
        callback.assert_awaited_once()
        # small_talk は注文処理パイプラインを通らず LLM 返答生成のみ呼ぶ
        mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_phone_order_status_inquiry_uses_common_branching(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.list_by_customer.return_value = [_make_current_order()]
        callback = AsyncMock()

        with patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke:
            result = await orch.process_order_message(
                message="今の注文は？",
                line_user_id="+81312345678",
                source=OrderSource.PHONE,
                response_callback=callback,
                known_customer_id="C-001",
                known_customer_name="ビストロ青葉",
            )

        assert "現在のご注文内容" in result["response"]
        assert "りんご" in result["response"]
        order_repo.list_by_customer.assert_awaited_once_with("C-001", limit=50)
        callback.assert_awaited_once()
        mock_invoke.assert_not_called()


class TestLineOrderCorrections:
    @pytest.mark.asyncio
    async def test_line_explicit_non_master_unit_requires_confirmation(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.fuzzy_match.return_value = Product(
            id="P-002",
            tenant_id="T-TEST",
            name="バナナ",
            default_unit=UnitType.KG,
            temperature_zone=TemperatureZone.AMBIENT,
        )
        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "ビストロ青葉",
                "items": [
                    {
                        "product_id": "P-002",
                        "product_name": "バナナ",
                        "quantity": 1,
                        "unit": "kg",
                        "temperature_zone": "常温",
                    }
                ],
                "needs_confirmation": False,
            },
            ensure_ascii=False,
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.1)
            if call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.1)
            return ("確認しました", 0.1)

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch("src.agents.orchestrator._check_draft_inventory", new_callable=AsyncMock) as mock_check,
        ):
            result = await orch.process_order_message(
                message="バナナ一個",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

        mock_check.assert_not_called()
        assert result["session_status"] == "awaiting_reply"
        assert "システム上は1kg" in result["response"]
        assert result["pending_order_draft"]["items"][0]["quantity"] == 1.0
        assert result["pending_order_draft"]["items"][0]["unit"] == "kg"

    @pytest.mark.asyncio
    async def test_line_box_order_converts_to_master_kg_when_unit_weight_exists(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.fuzzy_match.return_value = Product(
            id="P-005",
            tenant_id="T-TEST",
            name="もも",
            default_unit=UnitType.KG,
            temperature_zone=TemperatureZone.CHILLED,
            unit_weight_kg=2.0,
        )
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders: list[Order] = []

        async def save_order(order: Order) -> str:
            saved_orders.append(order)
            return "ORD-PEACH-KG"

        order_repo.save = AsyncMock(side_effect=save_order)
        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "ビストロ青葉",
                "items": [
                    {
                        "product_id": "P-005",
                        "product_name": "もも",
                        "quantity": 1,
                        "unit": "箱",
                        "temperature_zone": "冷蔵",
                    }
                ],
                "needs_confirmation": False,
            },
            ensure_ascii=False,
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.1)
            if call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.1)
            return ("確認しました", 0.1)

        checked_items = [
            {
                "product_id": "P-005",
                "product_name": "もも",
                "required_qty": 2.0,
                "unit": "kg",
                "available_qty": 10,
                "is_sufficient": True,
                "needs_confirmation": False,
            }
        ]

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch("src.agents.orchestrator._check_draft_inventory", return_value=checked_items),
        ):
            result = await orch.process_order_message(
                message="もも1箱",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

        assert result["order_id"] == "ORD-PEACH-KG"
        assert saved_orders[0].items[0].quantity == 2.0
        assert saved_orders[0].items[0].unit == "kg"

    @pytest.mark.asyncio
    async def test_line_kg_order_for_box_master_confirms_internal_box_unit(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.fuzzy_match.return_value = Product(
            id="P-005",
            tenant_id="T-TEST",
            name="もも",
            default_unit=UnitType.BOX,
            temperature_zone=TemperatureZone.CHILLED,
            unit_weight_kg=2.0,
        )
        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "ビストロ青葉",
                "items": [
                    {
                        "product_id": "P-005",
                        "product_name": "もも",
                        "quantity": 1,
                        "unit": "kg",
                        "temperature_zone": "冷蔵",
                    }
                ],
                "needs_confirmation": False,
            },
            ensure_ascii=False,
        )

        async def mock_invoke(agent, message):
            return (f"```json\n{intake_json}\n```", 0.1)

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch("src.agents.orchestrator._check_draft_inventory", new_callable=AsyncMock) as mock_check,
        ):
            result = await orch.process_order_message(
                message="もも1kg",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

        mock_check.assert_not_called()
        assert result["session_status"] == "awaiting_reply"
        assert "システム上は1箱" in result["response"]
        assert result["pending_order_draft"]["items"][0]["quantity"] == 1.0
        assert result["pending_order_draft"]["items"][0]["unit"] == "箱"

    @pytest.mark.asyncio
    async def test_line_watermelon_order_with_stock_is_accepted(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.fuzzy_match.return_value = Product(
            id="P-008",
            tenant_id="T-TEST",
            name="スイカ",
            default_unit=UnitType.PIECE,
            temperature_zone=TemperatureZone.AMBIENT,
        )
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders: list[Order] = []

        async def save_order(order: Order) -> str:
            saved_orders.append(order)
            return "ORD-WATERMELON"

        order_repo.save = AsyncMock(side_effect=save_order)
        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "ビストロ青葉",
                "items": [
                    {
                        "product_id": "P-008",
                        "product_name": "スイカ",
                        "quantity": 1,
                        "unit": "個",
                        "temperature_zone": "常温",
                    }
                ],
                "needs_confirmation": False,
            },
            ensure_ascii=False,
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.1)
            if call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.1)
            return ("確認しました", 0.1)

        checked_items = [
            {
                "product_id": "P-008",
                "product_name": "スイカ",
                "required_qty": 1.0,
                "unit": "個",
                "available_qty": 10,
                "is_sufficient": True,
                "needs_confirmation": False,
            }
        ]

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch("src.agents.orchestrator._check_draft_inventory", return_value=checked_items),
        ):
            result = await orch.process_order_message(
                message="スイカ一個",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

        assert result["order_id"] == "ORD-WATERMELON"
        assert "在庫が0" not in result["response"]
        assert saved_orders[0].items[0].product_id == "P-008"
        assert saved_orders[0].items[0].quantity == 1.0
        assert saved_orders[0].items[0].unit == "個"

    @pytest.mark.asyncio
    async def test_line_quantity_reply_updates_single_pending_item_without_llm(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        product_master = mock_tenant_ctx.get_connector("IProductMaster")
        product_master.get_by_id.return_value = Product(
            id="P-005",
            tenant_id="T-TEST",
            name="もも",
            default_unit=UnitType.KG,
            temperature_zone=TemperatureZone.CHILLED,
        )
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders: list[Order] = []

        async def save_order(order: Order) -> str:
            saved_orders.append(order)
            return "ORD-PEACH"

        order_repo.save = AsyncMock(side_effect=save_order)
        pending_draft = {
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
            "items": [
                {
                    "product_id": "P-005",
                    "product_name": "もも",
                    "quantity": 1,
                    "unit": "個",
                    "temperature_zone": "冷蔵",
                }
            ],
        }
        checked_items = [
            {
                "product_id": "P-005",
                "product_name": "もも",
                "required_qty": 1.0,
                "unit": "kg",
                "available_qty": 10,
                "is_sufficient": True,
                "needs_confirmation": False,
            }
        ]

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch("src.agents.orchestrator._check_draft_inventory", return_value=checked_items),
        ):
            result = await orch.process_order_message(
                message="1kg",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                pending_order_draft=pending_draft,
                session_id="sess-1",
            )

        mock_invoke.assert_not_called()
        assert result["order_id"] == "ORD-PEACH"
        assert saved_orders[0].items[0].product_name == "もも"
        assert saved_orders[0].items[0].quantity == 1.0
        assert saved_orders[0].items[0].unit == "kg"


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

    def test_skips_policy_for_full_cancel_intent(self):
        response = "キャンセルを承りました。ご注文を取り消しいたしました。"

        # FULL_CANCEL のときは「承りました」を含んでいても書き換えない
        result = _enforce_response_policy(
            response,
            needs_confirmation=True,
            inventory_needs_review=False,
            intent=OrderIntent.FULL_CANCEL,
        )
        assert result == response

    def test_skips_policy_for_partial_cancel_intent(self):
        response = "一部キャンセルを承りました。"

        result = _enforce_response_policy(
            response,
            needs_confirmation=True,
            inventory_needs_review=False,
            intent=OrderIntent.PARTIAL_CANCEL,
        )
        assert result == response

    def test_applies_policy_for_new_order_intent_with_confirmation_needed(self):
        response = "ご注文承りました。りんご150kgで確定しました。"

        result = _enforce_response_policy(
            response,
            needs_confirmation=True,
            inventory_needs_review=False,
            intent=OrderIntent.NEW_ORDER,
        )
        assert result != response
        assert "確認が必要" in result

    def test_phone_specific_message_when_needs_confirmation(self):
        response = "ご注文承りました。"

        result = _enforce_response_policy(
            response,
            needs_confirmation=True,
            inventory_needs_review=False,
            source=OrderSource.PHONE,
            intent=OrderIntent.NEW_ORDER,
        )
        assert "担当者が改めてご連絡" in result
        assert "返信してください" not in result


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
    async def test_create_order_from_draft_uses_jst_business_date(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders: list[Order] = []

        async def save_order(order: Order) -> str:
            saved_orders.append(order)
            return "ORD-JST"

        order_repo.save = AsyncMock(side_effect=save_order)
        draft = {
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 5,
                    "unit": "箱",
                    "temperature_zone": "冷蔵",
                }
            ],
        }

        with patch("src.agents.orchestrator.today_jst", return_value=date(2026, 5, 26)):
            order = await orch.create_order_from_draft(draft, source=OrderSource.LINE)

        assert order.id == "ORD-JST"
        assert saved_orders[0].order_date == date(2026, 5, 26)
        assert saved_orders[0].delivery_date == date(2026, 5, 26)

    @pytest.mark.asyncio
    async def test_sends_once_on_intake_fallback(self, mock_tenant_ctx):
        """When intake returns no parseable draft, orchestrator sends one message."""
        orch = _make_orchestrator(mock_tenant_ctx)

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            mock_invoke.return_value = ("すみません、理解できませんでした。", 0.5)

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
                "customer_name": "ビストロ青葉",
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
                return (f"```json\n{intake_json}\n```", 0.5)
            elif call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.3)
            elif call_count == 3:
                return ('```json\n{"all_reserved": true}\n```', 0.3)
            else:
                return ("ご注文承りました。りんご1個ですね。", 0.5)

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
                "customer_name": "ビストロ青葉",
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
                return (f"```json\n{intake_json}\n```", 0.5)
            elif call_count == 2:
                return ('```json\n{"anomalies": [{"type": "quantity"}], "confirmation_needed": true}\n```', 0.3)
            else:
                return ("りんご150kgは通常より多いですが、よろしいですか？", 0.5)

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
            "customer_name": "ビストロ青葉",
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
            mock_invoke.return_value = ("ご注文を確定しました。", 0.5)

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
            assert "受注No:" not in result["response"]

    @pytest.mark.asyncio
    async def test_full_cancel_updates_current_order_without_agent_call(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.update_status = AsyncMock()
        current_order = Order(
            uid="ORD-CURRENT",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="テスト社",
            order_date=date.today(),
            delivery_date=date.today(),
            source=OrderSource.LINE,
            status=OrderStatus.ACCEPTED,
            items=[
                OrderItem(
                    product_id="P-001",
                    product_name="りんご",
                    quantity=1,
                    unit="箱",
                    temperature_zone=TemperatureZone.CHILLED,
                )
            ],
        )

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock) as mock_invoke,
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
        ):
            result = await orch.process_order_message(
                message="全部キャンセルでお願いします",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                current_order=current_order,
            )

            order_repo.update_status.assert_awaited_once_with("T-TEST", "ORD-CURRENT", OrderStatus.CANCELLED)
            mock_invoke.assert_not_called()
            mock_send.assert_awaited_once()
            assert result["current_order_cleared"] is True
            assert "受注No:" not in result["response"]

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
                "customer_name": "ビストロ青葉",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 10, "unit": "箱"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.5)
            if call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.3)
            return ("OK", 0.1)

        # 在庫0 → 完全欠品
        mock_checked_items = [
            {
                "product_id": "P-001",
                "product_name": "りんご",
                "required_qty": 10.0,
                "unit": "箱",
                "available_qty": 0,
                "is_sufficient": False,
                "needs_confirmation": True,
            }
        ]

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send,
            patch("src.agents.orchestrator._check_draft_inventory", return_value=mock_checked_items),
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
            assert saved_orders[0].status == OrderStatus.NEEDS_REVIEW
            assert "在庫切れ" in saved_orders[0].remarks
            assert saved_orders[0].session_id == "sess-review"
            assert mock_send.call_count == 1
            assert "在庫が0箱" in result["response"]

    @pytest.mark.asyncio
    async def test_inventory_shortage_uses_template_not_llm(self, mock_tenant_ctx):
        """在庫不足時はテンプレート返答が使われ、LLM生成の不安全な返答は出力されない。"""
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-REVIEW")

        intake_json = json.dumps(
            {
                "customer_id": "C-001",
                "customer_name": "ビストロ青葉",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 10, "unit": "箱"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.5)
            if call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.3)
            return ("OK", 0.1)

        # 部分在庫 → テンプレート返答で「よろしいですか？」
        mock_checked_items = [
            {
                "product_id": "P-001",
                "product_name": "りんご",
                "required_qty": 10.0,
                "unit": "箱",
                "available_qty": 5,
                "is_sufficient": False,
                "needs_confirmation": True,
            }
        ]

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch("src.agents.orchestrator._check_draft_inventory", return_value=mock_checked_items),
        ):
            result = await orch.process_order_message(
                message="りんご10箱",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
            )

            normalized = result["response"].replace(" ", "")
            assert all(pattern not in normalized for pattern in FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS)
            assert "よろしいですか" in result["response"]
            assert "5箱" in result["response"]


class TestStockShortageInsist:
    """B-15: 在庫不足提示後に顧客が強要望した場合、元数量で要対応注文を作成しエスカレートする。"""

    @pytest.mark.asyncio
    async def test_insist_creates_review_order_with_original_quantity(self, mock_tenant_ctx):
        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        saved_orders: list[Order] = []

        async def save_order(order: Order) -> str:
            saved_orders.append(order)
            return "ORD-INSIST"

        order_repo.save = AsyncMock(side_effect=save_order)

        pending_order_draft = {
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 80,
                    "unit": "箱",
                    "temperature_zone": "冷蔵",
                }
            ],
            "inventory_checked": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "required_qty": 80,
                    "unit": "箱",
                    "available_qty": 50,
                    "is_sufficient": False,
                    "needs_confirmation": True,
                }
            ],
        }

        with patch.object(orch, "_send_line_message", new_callable=AsyncMock) as mock_send:
            result = await orch.process_order_message(
                message="どうしても80箱必要なので、なんとかお願いします",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                session_id="sess-insist",
                pending_order_draft=pending_order_draft,
            )

        assert mock_send.call_count == 1
        assert len(saved_orders) == 1
        saved = saved_orders[0]
        assert saved.status == OrderStatus.NEEDS_REVIEW
        assert "顧客強要望" in (saved.remarks or "")
        assert saved.items[0].quantity == 80
        assert saved.items[0].product_id == "P-001"
        assert result.get("review_order_id") == "ORD-INSIST"
        assert result.get("pending_order_draft") is None
        assert "担当者が確認" in result["response"]
        assert "りんご 80箱" in result["response"]
        # 確定表現は出力しない
        normalized = result["response"].replace(" ", "")
        assert all(pattern not in normalized for pattern in FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS)

    @pytest.mark.asyncio
    async def test_skip_when_intent_is_not_insist(self, mock_tenant_ctx):
        """intent が INSIST_ON_SHORTAGE でないときは B-15 ハンドラを通らない。

        『はい』など単純な肯定返信を Intent 分類器（LLM 含む）が non-insist に判定した場合に、
        強要望ハンドラが呼ばれず NEEDS_REVIEW 受注も作成されないことを担保する。
        """
        from src.services.intent_understanding import IntentResult

        orch = _make_orchestrator(mock_tenant_ctx)
        order_repo = mock_tenant_ctx.get_connector("IOrderRepository")
        order_repo.save = AsyncMock(return_value="ORD-OTHER")

        pending_order_draft = {
            "customer_id": "C-001",
            "customer_name": "ビストロ青葉",
            "items": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "quantity": 80,
                    "unit": "箱",
                    "temperature_zone": "冷蔵",
                }
            ],
            "inventory_checked": [
                {
                    "product_id": "P-001",
                    "product_name": "りんご",
                    "required_qty": 80,
                    "unit": "箱",
                    "available_qty": 50,
                    "is_sufficient": False,
                    "needs_confirmation": True,
                }
            ],
        }

        async def _fake_classify_intent(message, *, source, has_current_order, has_pending_shortage=False):
            assert has_pending_shortage is True  # 強要望チェックが scope されている
            return IntentResult(intent=OrderIntent.UNCLEAR, confidence=0.5)

        with (
            patch.object(orch, "_classify_intent", side_effect=_fake_classify_intent),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock, return_value=("noop", 0.1)),
            patch("src.agents.orchestrator._check_draft_inventory", return_value=[]),
        ):
            result = await orch.process_order_message(
                message="はい",
                line_user_id="U123",
                reply_token="tok",
                source=OrderSource.LINE,
                session_id="sess-affirm",
                pending_order_draft=pending_order_draft,
            )

        # 強要望ハンドラを通っていないことを確認（顧客向け文言が違う）
        assert "担当者が確認のうえ、改めてご連絡いたします" not in (result.get("response") or "")


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
                "customer_name": "ビストロ青葉",
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
                return (f"```json\n{intake_json}\n```", 0.5)
            elif call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.3)
            elif call_count == 3:
                return ('```json\n{"all_reserved": true}\n```', 0.3)
            else:
                return ("りんご1個、承りました。", 0.5)

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
            customer_name="ビストロ青葉",
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
            "customer_name": "ビストロ青葉",
            "items": [
                {"product_id": "P-001", "product_name": "りんご", "quantity": 5, "unit": "箱"},
            ],
        }

        with (
            patch.object(orch, "_invoke_agent", new_callable=AsyncMock, return_value=("ご注文を確定しました。", 0.5)),
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
                "customer_name": "ビストロ青葉",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 1, "unit": "個"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.5)
            elif call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.3)
            elif call_count == 3:
                return ('```json\n{"all_reserved": true}\n```', 0.3)
            else:
                return ("りんご1個、承りました。", 0.5)

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
                "customer_name": "ビストロ青葉",
                "items": [{"product_id": "P-001", "product_name": "りんご", "quantity": 10, "unit": "箱"}],
                "needs_confirmation": False,
            }
        )

        call_count = 0

        async def mock_invoke(agent, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (f"```json\n{intake_json}\n```", 0.5)
            if call_count == 2:
                return ('```json\n{"anomalies": [], "confirmation_needed": false}\n```', 0.3)
            return ("OK", 0.1)

        mock_checked_items = [
            {
                "product_id": "P-001",
                "product_name": "りんご",
                "required_qty": 10.0,
                "unit": "箱",
                "available_qty": 0,
                "is_sufficient": False,
                "needs_confirmation": True,
            }
        ]

        with (
            patch.object(orch, "_invoke_agent", side_effect=mock_invoke),
            patch.object(orch, "_send_line_message", new_callable=AsyncMock),
            patch.object(orch, "_run_learning", new_callable=AsyncMock) as mock_learn,
            patch("src.agents.orchestrator._check_draft_inventory", return_value=mock_checked_items),
        ):
            await orch.process_order_message(
                message="りんご10箱",
                line_user_id="U123",
                source=OrderSource.LINE,
            )

            mock_learn.assert_not_called()


class TestClassifyAdditionalOrder:
    """_classify_additional_order 判定関数の純粋関数テスト。"""

    def _make_order(
        self,
        delivery_date: date | None = None,
        status: OrderStatus = OrderStatus.ACCEPTED,
        product_id: str = "P-001",
        quantity: float = 5.0,
        unit: str = "箱",
    ) -> Order:
        from src.utils.business_date import today_jst

        return Order(
            uid="ORD-TEST",
            tenant_id="T-TEST",
            customer_id="C-001",
            customer_name="テスト社",
            order_date=today_jst(),
            delivery_date=delivery_date or today_jst(),
            source=OrderSource.LINE,
            status=status,
            items=[
                OrderItem(
                    product_id=product_id,
                    product_name="りんご",
                    quantity=quantity,
                    unit=unit,
                    temperature_zone=TemperatureZone.CHILLED,
                )
            ],
        )

    def _make_draft(
        self,
        delivery_date: date | str | None = None,
        product_id: str = "P-002",
        quantity: float = 3.0,
        unit: str = "kg",
    ) -> dict:
        from src.utils.business_date import today_jst

        dd = delivery_date if delivery_date is not None else today_jst()
        return {
            "customer_id": "C-001",
            "delivery_date": dd,
            "items": [
                {
                    "product_id": product_id,
                    "product_name": "バナナ",
                    "quantity": quantity,
                    "unit": unit,
                    "temperature_zone": "常温",
                }
            ],
        }

    def test_no_current_order_returns_new(self):
        draft = self._make_draft()
        plan = _classify_additional_order(None, draft, editable=False)
        assert plan.mode == "new"
        assert plan.use_existing_order is False

    def test_not_editable_returns_new(self):
        order = self._make_order(status=OrderStatus.SHIPPING)
        draft = self._make_draft()
        plan = _classify_additional_order(order, draft, editable=False)
        assert plan.mode == "new"
        assert plan.use_existing_order is False

    def test_different_delivery_date_returns_new(self):
        from datetime import timedelta
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst())
        draft = self._make_draft(delivery_date=today_jst() + timedelta(days=1))
        plan = _classify_additional_order(order, draft, editable=True)
        assert plan.mode == "new"
        assert plan.use_existing_order is False

    def test_same_date_no_overlap_returns_add(self):
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst(), product_id="P-001")
        draft = self._make_draft(delivery_date=today_jst(), product_id="P-002")
        plan = _classify_additional_order(order, draft, editable=True)
        assert plan.mode == "add"
        assert plan.use_existing_order is True
        assert len(plan.added_items) == 1
        # merged_items は既存1件 + 新規1件 = 2件
        assert len(plan.merged_items) == 2

    def test_same_date_overlap_returns_confirm_overlap(self):
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst(), product_id="P-001", quantity=9.0, unit="kg")
        draft = self._make_draft(delivery_date=today_jst(), product_id="P-001", quantity=9.0, unit="kg")
        plan = _classify_additional_order(order, draft, editable=True)
        assert plan.mode == "confirm_overlap"
        assert plan.use_existing_order is True
        assert len(plan.overlap_items) == 1
        ov = plan.overlap_items[0]
        assert ov["existing_qty"] == 9.0
        assert ov["add_qty"] == 9.0
        assert ov["total_qty"] == 18.0
        # merged_items の数量が合算されている
        merged_by_pid = {it["product_id"]: it for it in plan.merged_items}
        assert merged_by_pid["P-001"]["quantity"] == 18.0

    def test_modify_mode_overlap_replaces_existing_quantity(self):
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst(), product_id="P-001", quantity=5.0, unit="箱")
        draft = self._make_draft(delivery_date=today_jst(), product_id="P-001", quantity=1000.0, unit="個")
        plan = _classify_additional_order(order, draft, editable=True, is_modify_mode=True)
        assert plan.mode == "replace"
        assert plan.use_existing_order is True
        assert plan.overlap_items == []
        merged_by_pid = {it["product_id"]: it for it in plan.merged_items}
        assert merged_by_pid["P-001"]["quantity"] == 1000.0
        assert merged_by_pid["P-001"]["unit"] == "個"

    def test_delivery_date_as_string_is_parsed(self):
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst(), product_id="P-001")
        draft = self._make_draft(
            delivery_date=today_jst().isoformat(),  # 文字列
            product_id="P-002",
        )
        plan = _classify_additional_order(order, draft, editable=True)
        assert plan.mode == "add"

    def test_add_mode_overlap_accumulates_quantity(self):
        """「追加で3箱」→ 既存5箱に3箱を加算して合計8箱になること。"""
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst(), product_id="P-001", quantity=5.0, unit="箱")
        draft = self._make_draft(delivery_date=today_jst(), product_id="P-001", quantity=3.0, unit="箱")
        plan = _classify_additional_order(order, draft, editable=True, is_modify_mode=True, is_add_mode=True)
        assert plan.mode == "add"
        assert plan.use_existing_order is True
        merged_by_pid = {it["product_id"]: it for it in plan.merged_items}
        assert merged_by_pid["P-001"]["quantity"] == 8.0

    def test_add_mode_no_overlap_adds_new_item(self):
        """「バナナ追加で3kg」→ 既存りんご5箱 + バナナ3kgになること。"""
        from src.utils.business_date import today_jst

        order = self._make_order(delivery_date=today_jst(), product_id="P-001", quantity=5.0, unit="箱")
        draft = self._make_draft(delivery_date=today_jst(), product_id="P-002", quantity=3.0, unit="kg")
        plan = _classify_additional_order(order, draft, editable=True, is_modify_mode=True, is_add_mode=True)
        assert plan.mode == "add"
        assert len(plan.merged_items) == 2


class TestIsNegativeReply:
    def test_negative_words(self):
        for msg in ["いいえ", "やめる", "やめます", "キャンセル", "結構です"]:
            assert _is_negative_reply(msg), f"{msg!r} should be negative"

    def test_affirmative_not_negative(self):
        for msg in ["はい", "お願いします", "大丈夫"]:
            assert not _is_negative_reply(msg), f"{msg!r} should not be negative"

    def test_with_number_not_negative(self):
        assert not _is_negative_reply("いや15kgで")


class TestAnomalySeveritySavePlan:
    """_evaluate_anomaly_severity / _decide_save_status の単体テスト。"""

    from src.agents.orchestrator import _decide_save_status  # noqa: E402

    def test_high_anomaly_returns_needs_review(self):
        from src.agents.orchestrator import _decide_save_status

        status = _decide_save_status(
            has_high_anomaly=True,
            has_partial_stock=False,
            has_only_out_of_stock=False,
        )
        assert status.value == "要対応"

    def test_partial_stock_returns_needs_review(self):
        from src.agents.orchestrator import _decide_save_status

        status = _decide_save_status(
            has_high_anomaly=False,
            has_partial_stock=True,
            has_only_out_of_stock=False,
        )
        assert status.value == "要対応"

    def test_out_of_stock_returns_needs_review(self):
        from src.agents.orchestrator import _decide_save_status

        status = _decide_save_status(
            has_high_anomaly=False,
            has_partial_stock=False,
            has_only_out_of_stock=True,
        )
        assert status.value == "要対応"

    def test_normal_returns_accepted(self):
        from src.agents.orchestrator import _decide_save_status

        status = _decide_save_status(
            has_high_anomaly=False,
            has_partial_stock=False,
            has_only_out_of_stock=False,
        )
        assert status.value == "受注済み"

    def test_medium_anomaly_alone_returns_accepted(self):
        from src.agents.orchestrator import _decide_save_status

        # medium は ACCEPTED で通す（remarks に警告だけ残す）
        status = _decide_save_status(
            has_high_anomaly=False,
            has_partial_stock=False,
            has_only_out_of_stock=False,
        )
        assert status.value == "受注済み"
