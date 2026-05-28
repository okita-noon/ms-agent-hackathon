from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import unicodedata
from datetime import date
from collections.abc import Awaitable, Callable
from pathlib import Path
from string import Template

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from src.agents.definitions import (
    get_communication_instructions,
    get_exception_instructions,
    get_intake_instructions,
    get_inventory_instructions,
    get_orchestrator_instructions,
    get_phone_instructions,
)
from src.connectors.context import TenantContext
from src.models.inbound import InboundMessage
from src.models.message_history import MessageHistory
from src.services import delivery_estimator
from src.models.customer import DeliveryLeadTime
from src.models.order import DeliveryRoute, Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.models.product import UnitType
from src.models.session import OrderSession
from src.models.intelligence import ResolvedItem
from src.plugins.communication_plugin import CommunicationPlugin
from src.plugins.exception_plugin import ExceptionPlugin
from src.plugins.intake_plugin import IntakePlugin, normalize_unit_in_text
from src.plugins.inventory_plugin import InventoryPlugin
from src.services.dashboard_events import dashboard_event_broker
from src.services.line_template_renderer import (
    build_delivery_estimate_line,
    format_line_order_items,
    render_line_template,
)
from src.services.intent_understanding import IntentResult, IntentUnderstandingService, OrderIntent, is_rule_full_cancel
from src.services.inventory_application import InventoryApplicationService
from src.services.order_application import EDITABLE_ORDER_STATUSES, OrderApplicationService
from src.services.order_memory import OrderMemoryService
from src.utils.business_date import today_jst

logger = logging.getLogger(__name__)

DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"
HISTORY_CONTEXT_LIMIT = 20

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "_templates"
_email_config_cache: dict | None = None


def _load_template(name: str) -> Template:
    path = _TEMPLATES_DIR / name
    return Template(path.read_text(encoding="utf-8"))


def _load_email_config() -> dict:
    global _email_config_cache  # noqa: PLW0603
    if _email_config_cache is None:
        path = _TEMPLATES_DIR / "メール設定.json"
        _email_config_cache = json.loads(path.read_text(encoding="utf-8"))
    return _email_config_cache


def _build_email_signature() -> str:
    cfg = _load_email_config().get("signature", {})
    company = cfg.get("company_name", "")
    dept = cfg.get("department", "")
    tel = cfg.get("tel", "")
    email = cfg.get("email", "")
    return f"\n\n──────────────\n{company} {dept}\nTEL: {tel}\nEmail: {email}\n──────────────\n"


def _build_email_subject(base_subject: str | None, order_id: str | None = None) -> str:
    cfg = _load_email_config().get("subject", {})
    subject = base_subject or cfg.get("default", "ご注文の確認")
    if not subject.startswith("Re: "):
        subject = f"Re: {subject}"
    if order_id:
        suffix_tpl = cfg.get("order_confirmed_suffix", "")
        if suffix_tpl:
            suffix = Template(suffix_tpl).safe_substitute(order_id=order_id)
            subject = f"{subject} {suffix}"
    return subject


def _insert_order_id(response_text: str, order_id: str) -> str:
    """電話の返信テキスト末尾に受注Noを付与する。LINEでは使わない。"""
    return f"{response_text}\n\n受注No: {order_id}"


def _source_to_channel(source: OrderSource) -> str:
    """OrderSource をナレッジチャネル名に変換する。"""
    if source == OrderSource.EMAIL:
        return "email"
    if source == OrderSource.PHONE:
        return "phone"
    return "line"


def _build_email_from_template(
    template_name: str,
    intake_draft: dict,
    delivery_estimate: str | None = None,
    body: str | None = None,
) -> str:
    tpl = _load_template(template_name)
    customer_name = intake_draft.get("customer_name", "お客")
    items = intake_draft.get("items", [])
    order_lines = "\n".join(
        f"・{it.get('product_name', '')}: {it.get('quantity', '')} {it.get('unit', '')}" for it in items
    )
    email_body = tpl.safe_substitute(
        customer_name=customer_name,
        company_name=customer_name,
        order_items=order_lines,
        delivery_estimate=delivery_estimate or "",
        body=body or "",
    )
    return email_body + _build_email_signature()


def _build_line_from_template(
    template_name: str,
    *,
    items: list[dict] | list[OrderItem] | None = None,
    delivery_estimate: str | None = None,
    time_slot: str | None = None,
    body: str | None = None,
    summary: str | None = None,
) -> str:
    return render_line_template(
        template_name,
        order_items=format_line_order_items(items),
        delivery_estimate_line=build_delivery_estimate_line(delivery_estimate, time_slot=time_slot),
        body=body or "",
        summary=summary or "",
    )


def _build_order_cancel_response(source: OrderSource, order: Order) -> str:
    if source == OrderSource.EMAIL:
        return _build_email_from_template(
            "メール返信_異常時.txt",
            {"customer_name": order.customer_name},
            body="現在のご注文をキャンセルいたしました。",
        )
    if source == OrderSource.LINE:
        return _build_line_from_template("order_full_cancel_confirm.txt", items=order.items)
    return "現在のご注文をキャンセルいたしました。"


def _build_order_locked_response(source: OrderSource, order: Order) -> str:
    if source == OrderSource.EMAIL:
        return _build_email_from_template(
            "メール返信_異常時.txt",
            {"customer_name": order.customer_name},
            body="このご注文はすでに処理が進んでいるため、自動で変更・キャンセルできません。担当者が確認いたします。",
        )
    if source == OrderSource.LINE:
        return _build_line_from_template("order_locked_need_review.txt")
    return "このご注文はすでに処理が進んでいるため、自動で変更・キャンセルできません。担当者が確認いたします。"


def _build_small_talk_response(
    source: OrderSource,
    message: str,
    *,
    pending_order_draft: dict | None = None,
    customer_name: str | None = None,
) -> str:
    if source == OrderSource.EMAIL:
        return _build_email_small_talk_response(
            message,
            pending_order_draft=pending_order_draft,
            customer_name=customer_name,
        )
    if source == OrderSource.PHONE:
        return _build_phone_small_talk_response(message, pending_order_draft=pending_order_draft)
    return _build_line_small_talk_response(message, pending_order_draft=pending_order_draft)


def _small_talk_base(message: str, *, channel: str) -> str:
    normalized = re.sub(r"\s+", "", message).lower()
    if any(word in normalized for word in ("天気", "晴れ", "暑い", "寒い", "雨")):
        return "本当に気持ちのよいお天気ですね。"
    if "ありがとう" in normalized or "助かります" in normalized:
        return "こちらこそありがとうございます。"
    if channel == "phone":
        return "お電話ありがとうございます。"
    return "ご連絡ありがとうございます。"


def _build_line_small_talk_response(message: str, *, pending_order_draft: dict | None = None) -> str:
    prompt = (
        "先ほどの確認中のご注文について、内容を送ってください。"
        if pending_order_draft
        else "ご注文がありましたら、商品名と数量を送ってください。"
    )
    return f"{_small_talk_base(message, channel='line')}{prompt}"


def _build_phone_small_talk_response(message: str, *, pending_order_draft: dict | None = None) -> str:
    prompt = (
        "先ほどの確認中のご注文について、お返事をお話しください。"
        if pending_order_draft
        else "ご注文がありましたら、商品名と数量をお話しください。"
    )
    return f"{_small_talk_base(message, channel='phone')}{prompt}"


def _build_email_small_talk_response(
    message: str,
    *,
    pending_order_draft: dict | None = None,
    customer_name: str | None = None,
) -> str:
    base = _small_talk_base(message, channel="email")
    prompt = (
        "先ほど確認中のご注文について、内容をご返信ください。"
        if pending_order_draft
        else "ご注文がございましたら、商品名・数量・ご希望納品日をお知らせください。"
    )
    return _build_email_from_template(
        "メール返信_異常時.txt",
        {"customer_name": customer_name or "お客"},
        body=f"{base}\n\n{prompt}",
    )


def _build_current_orders_response(source: OrderSource, summary: str, *, customer_name: str | None = None) -> str:
    if source == OrderSource.LINE:
        return _build_line_from_template("order_current_summary.txt", summary=summary)
    if source == OrderSource.EMAIL:
        return _build_email_from_template(
            "メール返信_異常時.txt",
            {"customer_name": customer_name or "お客"},
            body=f"現在のご注文内容です。\n\n{summary}",
        )
    return f"現在のご注文内容です。{summary}"


def _build_no_current_order_response(source: OrderSource, *, customer_name: str | None = None) -> str:
    body = "変更対象の現在注文が見当たりませんでした。新しいご注文として承る場合は、商品名と数量をお知らせください。"
    if source == OrderSource.LINE:
        return _build_line_from_template("order_no_current_order.txt")
    if source == OrderSource.EMAIL:
        return _build_email_from_template(
            "メール返信_異常時.txt",
            {"customer_name": customer_name or "お客"},
            body=body,
        )
    return body


class OrderOrchestrator:
    def __init__(
        self,
        tenant_ctx: TenantContext,
        azure_openai_endpoint: str,
        azure_openai_key: str,
        deployment_name: str = DEFAULT_AZURE_OPENAI_DEPLOYMENT,
        use_multi_agent: bool | None = None,
    ):
        self._ctx = tenant_ctx
        self._endpoint = azure_openai_endpoint
        self._key = azure_openai_key
        self._deployment = deployment_name
        if use_multi_agent is None:
            self._use_multi_agent = os.getenv("USE_MULTI_AGENT", "true").lower() == "true"
        else:
            self._use_multi_agent = use_multi_agent

    def _build_kernel(self, *plugins: tuple[object, str]) -> Kernel:
        kernel = Kernel()
        kernel.add_service(
            AzureChatCompletion(
                deployment_name=self._deployment,
                endpoint=self._endpoint,
                api_key=self._key,
            )
        )
        for plugin_instance, plugin_name in plugins:
            kernel.add_plugin(plugin_instance, plugin_name=plugin_name)
        return kernel

    def _make_intake_agent(self, channel: str = "line") -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (IntakePlugin(self._ctx), "intake"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="IntakeAgent",
            instructions=get_intake_instructions(channel),
        )

    def _make_exception_agent(self, channel: str = "line") -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (ExceptionPlugin(self._ctx), "exception"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="ExceptionAgent",
            instructions=get_exception_instructions(channel),
        )

    def _make_inventory_agent(self, channel: str = "line") -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (InventoryPlugin(self._ctx), "inventory"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="InventoryAgent",
            instructions=get_inventory_instructions(channel),
        )

    def _make_communication_agent(self, channel: str = "line") -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (CommunicationPlugin(self._ctx), "communication"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="CommunicationAgent",
            instructions=get_communication_instructions(channel),
        )

    def _make_phone_order_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (IntakePlugin(self._ctx), "intake"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="PhoneOrderAgent",
            instructions=get_phone_instructions(),
        )

    def _make_orchestrator_agent(self, channel: str = "line") -> ChatCompletionAgent:
        # Shared kernel with all plugins for final response generation
        kernel = self._build_kernel(
            (IntakePlugin(self._ctx), "intake"),
            (InventoryPlugin(self._ctx), "inventory"),
            (ExceptionPlugin(self._ctx), "exception"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="Orchestrator",
            instructions=get_orchestrator_instructions(channel),
        )

    def _extract_json(self, text: str) -> dict | None:
        # Try to extract JSON block from agent output
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            raw = match.group(1)
        else:
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            raw = match.group(1) if match else None

        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def _invoke_agent(self, agent: ChatCompletionAgent, message: str) -> tuple[str, float]:
        """Agent を呼び出し、(応答テキスト, 所要秒数) を返す."""
        import time

        t0 = time.monotonic()
        result_text = ""
        thread = None
        async for response in agent.invoke(messages=message, thread=thread):
            result_text = str(response.content)
            thread = response.thread
        elapsed = round(time.monotonic() - t0, 2)
        return result_text, elapsed

    async def process_order_message(
        self,
        message: str,
        line_user_id: str,
        reply_token: str | None = None,
        source: OrderSource = OrderSource.LINE,
        response_callback: Callable[[str], Awaitable[None]] | None = None,
        conversation_history: list[MessageHistory] | None = None,
        pending_order_draft: dict | None = None,
        session_id: str | None = None,
        known_customer_id: str | None = None,
        known_customer_name: str | None = None,
        current_order: Order | None = None,
    ) -> dict:
        result: dict = {
            "response": "",
            "line_user_id": line_user_id,
            "reply_token": reply_token,
        }
        debug_log: list[str] = []
        result["debug_log"] = debug_log
        self._ctx._debug_log = debug_log
        # 数字の直後の単位表記ゆれを正規化（例: 10コ→10個、10キロ→10kg）
        normalized_message = normalize_unit_in_text(message)
        if normalized_message != message:
            debug_log.append(f"[単位正規化] {message!r} → {normalized_message!r}")
            message = normalized_message
        debug_log.append(f"[入力] source={source.value}, session={session_id}, message={message!r}")
        if known_customer_id:
            debug_log.append(f"[顧客] known渡し: customer_id={known_customer_id}, customer_name={known_customer_name}")
        else:
            debug_log.append(f"[顧客] known未渡し: line_user_id={line_user_id} で解決を試みる")
        if conversation_history:
            debug_log.append(f"[履歴] {len(conversation_history)}件の会話履歴あり")
        if pending_order_draft:
            draft_items = pending_order_draft.get("items", [])
            draft_cid = pending_order_draft.get("customer_id", "なし")
            debug_log.append(
                f"[ドラフト] 確認待ち注文ドラフトあり: customer_id={draft_cid}, items={len(draft_items)}件"
            )
        if current_order:
            debug_log.append(
                f"[現在注文] {current_order.id} (status={current_order.status.value}, customer_id={current_order.customer_id})"
            )
        intent_result = await self._classify_intent(message, source=source, has_current_order=current_order is not None)
        line_action_type = _line_action_type_from_intent(intent_result.intent, current_order=current_order)
        current_order_editable = _is_order_editable(current_order)
        debug_log.append(
            f"[分類] intent={intent_result.intent.value}, action_type={line_action_type}, "
            f"confidence={intent_result.confidence}, editable={current_order_editable}"
        )

        if intent_result.intent == OrderIntent.SMALL_TALK:
            debug_log.append("[判定] 雑談・挨拶として応答")
            response_text = _build_small_talk_response(
                source,
                message,
                pending_order_draft=pending_order_draft,
                customer_name=known_customer_name,
            )
            result.update(
                {
                    "response": response_text,
                    "intent": OrderIntent.SMALL_TALK.value,
                    "customer_id": known_customer_id,
                }
            )
            if pending_order_draft:
                result["session_status"] = "awaiting_reply"
                result["pending_order_draft"] = pending_order_draft
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        if intent_result.intent == OrderIntent.ORDER_STATUS_INQUIRY:
            debug_log.append("[判定] 現在注文の問い合わせと判定")
            customer_id = await self._resolve_customer_id_for_status(
                source=source,
                channel_user_id=line_user_id,
                known_customer_id=known_customer_id,
                current_order=current_order,
                debug_log=debug_log,
            )
            if customer_id:
                repo = self._ctx.get_connector("IOrderRepository")
                customer_orders = await repo.list_by_customer(customer_id, limit=50)
                today = today_jst()
                open_orders = [
                    o
                    for o in customer_orders
                    if o.status == OrderStatus.ACCEPTED and (o.delivery_date is None or o.delivery_date >= today)
                ]
                debug_log.append(f"[注文照会] list_by_customerで{len(open_orders)}件取得（ACCEPTED・今日以降）")
                if open_orders:
                    response_text = _build_current_orders_response(
                        source,
                        summary=_format_open_orders_summary(open_orders),
                        customer_name=known_customer_name,
                    )
                    result.update({"response": response_text, "customer_id": customer_id})
                    if response_callback:
                        await response_callback(response_text)
                    else:
                        await self._send_line_message(response_text, reply_token, line_user_id)
                    return result
            response_text = _build_no_current_order_response(source, customer_name=known_customer_name)
            result.update({"response": response_text, "pending_action_type": line_action_type})
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        if pending_order_draft:
            _affirmative = _is_affirmative_reply(message)
            if _affirmative:
                debug_log.append(f"[判定] 肯定返答 → ドラフト受注確定 (message={message!r})")
            else:
                debug_log.append(f"[判定] ドラフトあるが肯定返答ではない (message={message!r})")
        else:
            _affirmative = False
        if pending_order_draft and not _affirmative:
            pending_quantity_result = await self._try_handle_pending_quantity_reply(
                message=message,
                line_user_id=line_user_id,
                reply_token=reply_token,
                source=source,
                response_callback=response_callback,
                pending_order_draft=pending_order_draft,
                session_id=session_id,
                current_order=current_order if current_order_editable else None,
                debug_log=debug_log,
            )
            if pending_quantity_result:
                result.update(pending_quantity_result)
                result["debug_log"] = debug_log
                return result
        if pending_order_draft and _affirmative:
            saved_order = await self.create_order_from_draft(
                pending_order_draft,
                source=source,
                session_id=session_id,
                existing_order=current_order if source == OrderSource.LINE and current_order_editable else None,
                status=OrderStatus.ACCEPTED,
            )
            asyncio.create_task(self._run_learning(saved_order, message))
            route = await _resolve_delivery_route_from_customer(pending_order_draft, self._ctx)
            lead_time = await _resolve_lead_time(pending_order_draft, self._ctx)
            min_d, max_d = delivery_estimator.estimate(
                route,
                lead_time=lead_time,
                tenant_config=self._ctx.config,
            )
            affirm_delivery_estimate = delivery_estimator.format_estimate(min_d, max_d)
            response_text = await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text="顧客が確認待ち注文に同意しました。保存済みドラフトを受注確定しました。",
                exception_text=None,
                inventory_text=None,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                delivery_estimate=affirm_delivery_estimate,
                current_order=current_order,
                debug_log=debug_log,
            )
            if source == OrderSource.LINE:
                response_text = _build_line_from_template(
                    "order_update_confirm.txt" if current_order else "order_confirm.txt",
                    items=saved_order.items,
                    delivery_estimate=affirm_delivery_estimate,
                    time_slot=saved_order.delivery_time_slot,
                )
            elif source != OrderSource.EMAIL:
                response_text = _insert_order_id(response_text, saved_order.id)
            result["response"] = response_text
            debug_log.append(f"[確定] ドラフト受注確定: {saved_order.id}")
            result["order_id"] = saved_order.id
            result["order_saved"] = True
            result["customer_id"] = saved_order.customer_id
            result["current_order_id"] = saved_order.id
            result["current_order_snapshot"] = _build_current_order_snapshot(saved_order)
            result["current_order_editable"] = _is_order_editable(saved_order)
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        inventory_inquiry_result = await self._try_handle_inventory_inquiry(
            message, source, current_order, debug_log=debug_log
        )
        if inventory_inquiry_result:
            debug_log.append("[判定] 在庫問い合わせと判定 → 在庫照会で回答")
        else:
            debug_log.append("[判定] 在庫問い合わせではない")
        if inventory_inquiry_result:
            response_text = inventory_inquiry_result["response"]
            result.update(inventory_inquiry_result)
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        memory_order_result = await self._try_handle_memory_order(
            intent=intent_result.intent,
            message=message,
            source=source,
            line_user_id=line_user_id,
            reply_token=reply_token,
            response_callback=response_callback,
            session_id=session_id,
            known_customer_id=known_customer_id,
            known_customer_name=known_customer_name,
            debug_log=debug_log,
        )
        if memory_order_result:
            result.update(memory_order_result)
            return result

        if current_order:
            if intent_result.intent == OrderIntent.FULL_CANCEL:
                debug_log.append("[判定] 全注文取消と判定")
                cancel_result = await OrderApplicationService(self._ctx).cancel_order(current_order)
                if cancel_result.cancelled:
                    debug_log.append(f"[取消] 注文キャンセル実行: {current_order.id}")
                    response_text = _build_order_cancel_response(source, current_order)
                    result.update(
                        {
                            "response": response_text,
                            "order_id": current_order.id,
                            "customer_id": current_order.customer_id,
                            "current_order_cleared": True,
                            "current_order_id": None,
                            "current_order_snapshot": None,
                            "current_order_editable": False,
                        }
                    )
                    if response_callback:
                        await response_callback(response_text)
                    else:
                        await self._send_line_message(response_text, reply_token, line_user_id)
                    return result

                debug_log.append("[取消] 注文ロック済み → 変更不可")
                response_text = _build_order_locked_response(source, current_order)
                result.update(
                    {
                        "response": response_text,
                        "customer_id": current_order.customer_id,
                        "current_order_id": current_order.id,
                        "current_order_snapshot": _build_current_order_snapshot(current_order),
                        "current_order_editable": False,
                    }
                )
                if response_callback:
                    await response_callback(response_text)
                else:
                    await self._send_line_message(response_text, reply_token, line_user_id)
                return result

            if source == OrderSource.LINE and not current_order_editable and _looks_like_order_update_request(message):
                debug_log.append("[判定] 変更要求だが注文ロック済み → 変更不可")
                response_text = _build_order_locked_response(source, current_order)
                result.update(
                    {
                        "response": response_text,
                        "customer_id": current_order.customer_id,
                        "current_order_id": current_order.id,
                        "current_order_snapshot": _build_current_order_snapshot(current_order),
                        "current_order_editable": False,
                    }
                )
                if response_callback:
                    await response_callback(response_text)
                else:
                    await self._send_line_message(response_text, reply_token, line_user_id)
                return result

        if source == OrderSource.LINE and not current_order and _looks_like_change_only_message(message):
            debug_log.append("[判定] 変更/取消要求だが現在注文なし")
            response_text = _build_line_from_template("order_no_current_order.txt")
            result.update({"response": response_text, "pending_action_type": line_action_type})
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        # ── Agent処理の分岐 ───────────────────────────────────────────────────
        if self._use_multi_agent:
            debug_log.append("[パイプライン] マルチエージェント")
            agent_result = await self._run_multi_agent_chain(
                message=message,
                line_user_id=line_user_id,
                reply_token=reply_token,
                source=source,
                response_callback=response_callback,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                session_id=session_id,
                known_customer_id=known_customer_id,
                known_customer_name=known_customer_name,
                current_order=current_order,
            )
        else:
            debug_log.append("[パイプライン] シングルエージェント")
            agent_result = await self._run_single_agent(
                message=message,
                line_user_id=line_user_id,
                reply_token=reply_token,
                source=source,
                response_callback=response_callback,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                session_id=session_id,
                known_customer_id=known_customer_id,
                known_customer_name=known_customer_name,
                current_order=current_order,
            )
        if source == OrderSource.LINE:
            agent_result.setdefault("pending_action_type", line_action_type)
        agent_debug = agent_result.pop("debug_log", [])
        debug_log.extend(agent_debug)
        result.update(agent_result)
        result["debug_log"] = debug_log
        return result

    async def _resolve_customer_id_for_status(
        self,
        *,
        source: OrderSource,
        channel_user_id: str,
        known_customer_id: str | None,
        current_order: Order | None,
        debug_log: list[str],
    ) -> str | None:
        customer_id = known_customer_id or (current_order.customer_id if current_order else None)
        if customer_id:
            cid_source = "known渡し" if known_customer_id else "current_order"
            debug_log.append(f"[顧客解決] 経路={cid_source}, customer_id={customer_id}")
            return customer_id

        customer_repo = self._ctx.get_connector("ICustomerRepository")
        customer = None
        if source == OrderSource.LINE:
            customer = await customer_repo.find_by_line_user_id(self._ctx.tenant_id, channel_user_id)
            debug_log.append(f"[顧客解決] 経路=LINE User ID検索, customer_id={(customer.id if customer else '未特定')}")
        elif source == OrderSource.EMAIL:
            customer = await customer_repo.find_by_email(self._ctx.tenant_id, channel_user_id)
            debug_log.append(f"[顧客解決] 経路=メール検索, customer_id={(customer.id if customer else '未特定')}")
        elif source == OrderSource.PHONE:
            customer = await customer_repo.find_by_identifier(self._ctx.tenant_id, channel_user_id)
            debug_log.append(f"[顧客解決] 経路=電話番号検索, customer_id={(customer.id if customer else '未特定')}")
        return customer.id if customer else None

    async def _classify_intent(self, message: str, *, source: OrderSource, has_current_order: bool) -> IntentResult:
        async def llm_classifier(prompt: str) -> str:
            agent = self._make_orchestrator_agent(_source_to_channel(source))
            text, _elapsed = await self._invoke_agent(agent, prompt)
            return text

        classifier = llm_classifier if has_current_order else None
        return await IntentUnderstandingService(classifier).classify(message, has_current_order=has_current_order)

    async def process_phone_order_with_inventory(
        self,
        message: str,
        caller_number: str,
        conversation_history: list[MessageHistory] | None = None,
        pending_order_draft: dict | None = None,
        known_customer_id: str | None = None,
        known_customer_name: str | None = None,
    ) -> dict:
        """電話中の同期応答用: 1 Agentで注文抽出し、在庫はコードで確認する."""
        memory_ctx = _format_memory_context(conversation_history, pending_order_draft)
        customer_ctx = ""
        if known_customer_id and known_customer_name:
            customer_ctx = f"顧客は特定済みです（customer_id={known_customer_id}, 名前={known_customer_name}）。\n"
        if pending_order_draft:
            prompt = (
                "以下は電話での確認質問への回答です。確認待ち注文ドラフトに回答内容を反映してください。\n"
                f"電話番号: {caller_number}\n"
                f"{customer_ctx}"
                f"{memory_ctx}"
                f"顧客の回答: {message}\n"
            )
        else:
            prompt = f"以下の電話注文を処理してください。\n電話番号: {caller_number}\n{customer_ctx}{memory_ctx}発話内容: {message}\n"

        intent_result = await IntentUnderstandingService().classify(message, has_current_order=False)
        if intent_result.intent == OrderIntent.SMALL_TALK:
            result = {
                "response": _build_small_talk_response(
                    OrderSource.PHONE,
                    message,
                    pending_order_draft=pending_order_draft,
                    customer_name=known_customer_name,
                ),
                "phone_sync_status": "small_talk",
                "order_accepted": False,
            }
            if pending_order_draft:
                result["pending_order_draft"] = pending_order_draft
                result["session_status"] = "awaiting_reply"
            return result

        if intent_result.intent == OrderIntent.ORDER_STATUS_INQUIRY:
            customer_id = known_customer_id
            customer_name = known_customer_name
            if not customer_id:
                try:
                    customer_repo = self._ctx.get_connector("ICustomerRepository")
                    customer = await customer_repo.find_by_identifier(self._ctx.tenant_id, caller_number)
                    if customer:
                        customer_id = customer.id
                        customer_name = customer.name
                except Exception:
                    logger.exception("Failed to resolve phone customer for order status inquiry")
            if customer_id:
                repo = self._ctx.get_connector("IOrderRepository")
                customer_orders = await repo.list_by_customer(customer_id, limit=50)
                today = today_jst()
                open_orders = [
                    o
                    for o in customer_orders
                    if o.status == OrderStatus.ACCEPTED and (o.delivery_date is None or o.delivery_date >= today)
                ]
                if open_orders:
                    response = _build_current_orders_response(
                        OrderSource.PHONE,
                        _format_open_orders_summary(open_orders),
                        customer_name=customer_name,
                    )
                    return {
                        "response": response,
                        "phone_sync_status": "order_status_inquiry",
                        "order_accepted": False,
                    }
            return {
                "response": _build_no_current_order_response(OrderSource.PHONE, customer_name=customer_name),
                "phone_sync_status": "order_status_inquiry",
                "order_accepted": False,
            }

        if pending_order_draft:
            quantity_reply = _extract_quantity_only_reply(message)
            target = _find_single_partial_inventory_target(pending_order_draft)
            if quantity_reply and target:
                quantity, unit = quantity_reply
                target_unit = target.get("unit") or ""
                if not unit or not target_unit or unit == target_unit:
                    draft = copy.deepcopy(pending_order_draft)
                    for item in draft.get("items", []) or []:
                        if item.get("product_id") == target.get("product_id"):
                            item["quantity"] = quantity
                            if unit:
                                item["unit"] = unit
                            break
                    draft.pop("inventory_checked", None)
                    return await self._build_phone_sync_inventory_result(draft=draft, intake_text="")

        if known_customer_id and (_is_usual_order_request(message) or _is_previous_order_request(message)):
            memory_service = OrderMemoryService(self._ctx)
            draft = (
                await memory_service.resolve_previous_order(known_customer_id)
                if _is_previous_order_request(message)
                else await memory_service.resolve_usual_order(known_customer_id, message)
            )
            if draft:
                if known_customer_name and not draft.get("customer_name"):
                    draft["customer_name"] = known_customer_name
                return await self._build_phone_sync_inventory_result(draft=draft, intake_text="")

        phone_agent = self._make_phone_order_agent()
        intake_text, _elapsed = await self._invoke_agent(phone_agent, prompt)
        logger.info("Phone agent responded in %.2fs", _elapsed)
        intake_draft = _apply_known_customer_to_intake(
            self._extract_json(intake_text),
            known_customer_id=known_customer_id,
            known_customer_name=known_customer_name,
        )

        if intake_draft.get("is_farewell"):
            return {
                "response": intake_draft.get("response", "ありがとうございます。失礼いたします。"),
                "phone_sync_status": "farewell",
            }

        draft = _build_draft_from_intake(intake_draft)

        if not draft:
            response = _format_phone_inventory_response(
                items=[],
                needs_confirmation=True,
                confirmation_message=intake_draft.get("confirmation_message")
                or "すみません、ご注文の商品と数量をもう一度お願いいたします。",
            )
            return {
                "response": response,
                "phone_sync_status": "needs_confirmation",
                "intake_text": intake_text,
                "pending_order_draft": None,
                "session_status": "awaiting_reply",
            }

        return await self._build_phone_sync_inventory_result(
            draft=draft,
            intake_text=intake_text,
            intake_draft=intake_draft,
        )

    async def _build_phone_sync_inventory_result(
        self,
        *,
        draft: dict,
        intake_text: str,
        intake_draft: dict | None = None,
    ) -> dict:
        invalid_quantity_items = _find_non_positive_quantity_items(draft)
        if invalid_quantity_items:
            response = _format_invalid_quantity_response(invalid_quantity_items, source=OrderSource.PHONE)
            return {
                "response": response,
                "phone_sync_status": "needs_confirmation",
                "intake_text": intake_text,
                "pending_order_draft": draft,
                "session_status": "awaiting_reply",
                "order_accepted": False,
            }

        inventory_results = await _check_draft_inventory(self._ctx, draft)
        needs_confirmation = bool((intake_draft or {}).get("needs_confirmation")) or any(
            item.get("needs_confirmation") for item in inventory_results
        )
        response = _format_phone_inventory_response(
            items=inventory_results,
            needs_confirmation=needs_confirmation,
            confirmation_message=(intake_draft or {}).get("confirmation_message"),
        )

        result = {
            "response": response,
            "phone_sync_status": "inventory_checked",
            "intake_draft": intake_draft or {},
            "pending_order_draft": draft,
            "inventory": inventory_results,
            "order_accepted": not needs_confirmation,
        }
        if needs_confirmation:
            result["session_status"] = "awaiting_reply"
            partial_stock = [
                item for item in inventory_results if item.get("available_qty") and not item.get("is_sufficient")
            ]
            if partial_stock:
                draft["inventory_checked"] = inventory_results
        return result

    async def _try_handle_memory_order(
        self,
        *,
        intent: OrderIntent,
        message: str,
        source: OrderSource,
        line_user_id: str,
        reply_token: str | None,
        response_callback: Callable[[str], Awaitable[None]] | None,
        session_id: str | None,
        known_customer_id: str | None,
        known_customer_name: str | None,
        debug_log: list[str] | None = None,
    ) -> dict | None:
        if intent not in {OrderIntent.REPEAT_PREVIOUS_ORDER, OrderIntent.REPEAT_USUAL_ORDER}:
            return None
        if not known_customer_id:
            if debug_log is not None:
                debug_log.append("[記憶注文] 顧客未特定のためスキップ")
            return None

        memory_service = OrderMemoryService(self._ctx)
        draft = (
            await memory_service.resolve_previous_order(known_customer_id)
            if intent == OrderIntent.REPEAT_PREVIOUS_ORDER
            else await memory_service.resolve_usual_order(known_customer_id, message)
        )
        if not draft:
            if debug_log is not None:
                debug_log.append(f"[記憶注文] {intent.value} に該当する注文パターンなし")
            return None

        draft["customer_id"] = known_customer_id
        if known_customer_name and not draft.get("customer_name"):
            draft["customer_name"] = known_customer_name
        if debug_log is not None:
            debug_log.append(f"[記憶注文] {intent.value} をドラフト復元: {len(draft.get('items', []))}件")

        invalid_quantity_items = _find_non_positive_quantity_items(draft)
        if invalid_quantity_items:
            response_text = _format_invalid_quantity_response(invalid_quantity_items, source=source)
            result = {
                "response": response_text,
                "customer_id": known_customer_id,
                "pending_order_draft": draft,
                "session_status": "awaiting_reply",
            }
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        checked_items = await _check_draft_inventory(self._ctx, draft)
        out_of_stock, partial_stock = _classify_inventory_shortage(checked_items)
        if out_of_stock or partial_stock:
            response_text = _build_inventory_shortage_response(
                checked_items,
                source=source,
            ) or _format_phone_inventory_response(
                checked_items,
                needs_confirmation=True,
            )
            result = {
                "response": response_text,
                "customer_id": known_customer_id,
                "pending_order_draft": draft,
                "inventory": checked_items,
            }
            if partial_stock:
                draft["inventory_checked"] = checked_items
                result["session_status"] = "awaiting_reply"
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        route = await _resolve_delivery_route_from_customer(draft, self._ctx)
        lead_time = await _resolve_lead_time(draft, self._ctx)
        min_d, max_d = delivery_estimator.estimate(
            route,
            lead_time=lead_time,
            tenant_config=self._ctx.config,
        )
        delivery_estimate_text = delivery_estimator.format_estimate(min_d, max_d)
        if not draft.get("delivery_date"):
            draft["delivery_date"] = min_d

        saved_order = await self.create_order_from_draft(
            draft,
            source=source,
            session_id=session_id,
            status=OrderStatus.ACCEPTED,
        )
        asyncio.create_task(self._run_learning(saved_order, message))

        if source == OrderSource.EMAIL:
            response_text = _build_email_from_template(
                "メール返信_受注確定.txt",
                draft,
                delivery_estimate=delivery_estimate_text,
            ).replace(
                "ご注文を承りました。",
                f"ご注文を承りました。（受注No: {saved_order.id}）",
            )
        elif source == OrderSource.LINE:
            response_text = _build_line_from_template(
                "order_confirm.txt",
                items=saved_order.items,
                delivery_estimate=delivery_estimate_text,
                time_slot=saved_order.delivery_time_slot,
            )
        else:
            response_text = _insert_order_id(
                _format_phone_inventory_response(checked_items, needs_confirmation=False),
                saved_order.id,
            )

        result = {
            "response": response_text,
            "order_id": saved_order.id,
            "order_saved": True,
            "customer_id": saved_order.customer_id,
            "current_order_id": saved_order.id,
            "current_order_snapshot": _build_current_order_snapshot(saved_order),
            "current_order_editable": _is_order_editable(saved_order),
        }
        if response_callback:
            await response_callback(response_text)
        else:
            await self._send_line_message(response_text, reply_token, line_user_id)
        return result

    async def _try_handle_pending_quantity_reply(
        self,
        *,
        message: str,
        line_user_id: str,
        reply_token: str | None,
        source: OrderSource,
        response_callback: Callable[[str], Awaitable[None]] | None,
        pending_order_draft: dict,
        session_id: str | None,
        current_order: Order | None,
        debug_log: list[str] | None = None,
    ) -> dict | None:
        updated_draft = await _apply_quantity_reply_to_single_pending_item(self._ctx, pending_order_draft, message)
        if not updated_draft:
            return None

        if debug_log is not None:
            item = updated_draft["items"][0]
            debug_log.append(
                "[ドラフト] 数量のみの返信を単一確認待ち商品へ反映: "
                f"{item.get('product_name')} {item.get('quantity')}{item.get('unit')}"
            )

        invalid_quantity_items = _find_non_positive_quantity_items(updated_draft)
        if invalid_quantity_items:
            response_text = _format_invalid_quantity_response(invalid_quantity_items, source=source)
            result = {
                "response": response_text,
                "customer_id": updated_draft.get("customer_id"),
                "pending_order_draft": updated_draft,
                "session_status": "awaiting_reply",
            }
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        if updated_draft.get("needs_confirmation"):
            response_text = updated_draft.get("confirmation_message") or "数量と単位をご確認ください。"
            result = {
                "response": response_text,
                "customer_id": updated_draft.get("customer_id"),
                "pending_order_draft": updated_draft,
                "session_status": "awaiting_reply",
            }
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        checked_items = await _check_draft_inventory(self._ctx, updated_draft)
        out_of_stock, partial_stock = _classify_inventory_shortage(checked_items)
        if out_of_stock or partial_stock:
            response_text = _build_inventory_shortage_response(
                checked_items,
                source=source,
            ) or _format_phone_inventory_response(
                checked_items,
                needs_confirmation=True,
            )
            result = {
                "response": response_text,
                "customer_id": updated_draft.get("customer_id"),
                "pending_order_draft": updated_draft,
                "inventory": checked_items,
            }
            if partial_stock:
                updated_draft["inventory_checked"] = checked_items
                result["session_status"] = "awaiting_reply"
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        route = await _resolve_delivery_route_from_customer(updated_draft, self._ctx)
        lead_time = await _resolve_lead_time(updated_draft, self._ctx)
        min_d, max_d = delivery_estimator.estimate(
            route,
            lead_time=lead_time,
            tenant_config=self._ctx.config,
        )
        delivery_estimate_text = delivery_estimator.format_estimate(min_d, max_d)
        if not updated_draft.get("delivery_date"):
            updated_draft["delivery_date"] = min_d

        saved_order = await self.create_order_from_draft(
            updated_draft,
            source=source,
            session_id=session_id,
            existing_order=current_order,
            status=OrderStatus.ACCEPTED,
        )
        asyncio.create_task(self._run_learning(saved_order, message))

        if source == OrderSource.EMAIL:
            response_text = _build_email_from_template(
                "メール返信_受注確定.txt",
                updated_draft,
                delivery_estimate=delivery_estimate_text,
            ).replace(
                "ご注文を承りました。",
                f"ご注文を承りました。（受注No: {saved_order.id}）",
            )
        elif source == OrderSource.LINE:
            response_text = _build_line_from_template(
                "order_update_confirm.txt" if current_order else "order_confirm.txt",
                items=saved_order.items,
                delivery_estimate=delivery_estimate_text,
                time_slot=saved_order.delivery_time_slot,
            )
        else:
            response_text = _insert_order_id(
                _format_phone_inventory_response(checked_items, needs_confirmation=False),
                saved_order.id,
            )

        result = {
            "response": response_text,
            "order_id": saved_order.id,
            "order_saved": True,
            "customer_id": saved_order.customer_id,
            "current_order_id": saved_order.id,
            "current_order_snapshot": _build_current_order_snapshot(saved_order),
            "current_order_editable": _is_order_editable(saved_order),
        }
        if response_callback:
            await response_callback(response_text)
        else:
            await self._send_line_message(response_text, reply_token, line_user_id)
        return result

    async def _run_single_agent(
        self,
        message: str,
        line_user_id: str,
        reply_token: str | None,
        source: OrderSource,
        response_callback: Callable[[str], Awaitable[None]] | None,
        conversation_history: list[MessageHistory] | None,
        pending_order_draft: dict | None,
        session_id: str | None,
        known_customer_id: str | None = None,
        known_customer_name: str | None = None,
        current_order: Order | None = None,
    ) -> dict:
        """旧ロジック: 単一Orchestrator Agentで全処理を実行する."""
        result: dict = {}
        debug_log: list[str] = []
        result["debug_log"] = debug_log
        self._ctx._debug_log = debug_log
        channel = _source_to_channel(source)

        # ── Step 1: Intake Agent ───────────────────────────────────────────────
        intake_agent = self._make_intake_agent(channel)
        if known_customer_id and known_customer_name:
            lookup_instruction = (
                f"顧客は特定済みです（customer_id={known_customer_id}, "
                f"customer_name={known_customer_name}）。顧客検索は不要です。"
            )
            user_label = f"メールアドレス: {line_user_id}"
            debug_log.append(
                f"[顧客解決] 経路=known渡し → Agentに顧客特定済みとして渡す: {known_customer_id} ({known_customer_name})"
            )
        elif source == OrderSource.PHONE:
            lookup_instruction = "lookup_customer でこの顧客を電話番号から特定し、"
            user_label = f"電話番号: {line_user_id}"
            debug_log.append(f"[顧客解決] 経路=電話番号lookup → Agent内で解決: {line_user_id}")
        elif source == OrderSource.EMAIL:
            lookup_instruction = "lookup_customer でこの顧客をメールアドレスから特定し、"
            user_label = f"メールアドレス: {line_user_id}"
            debug_log.append(f"[顧客解決] 経路=メールlookup → Agent内で解決: {line_user_id}")
        else:
            lookup_instruction = "lookup_customer_by_line_id でこの顧客を特定し、"
            user_label = f"LINE User ID: {line_user_id}"
            debug_log.append(f"[顧客解決] 経路=LINE User ID lookup → Agent内で解決: {line_user_id}")

        memory_ctx = _format_memory_context(conversation_history, pending_order_draft, current_order)
        debug_log.append(
            f"[コンテキスト] 履歴={len(conversation_history) if conversation_history else 0}件, "
            f"memory_ctx={len(memory_ctx)}文字"
        )
        if pending_order_draft:
            intake_mode = "ドラフト反映"
            intake_prompt = (
                f"以下は確認質問への顧客の回答です。確認待ち注文ドラフトに回答内容を反映してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"顧客の回答: {message}\n\n"
                f"まず {lookup_instruction}"
                f"次にドラフトに回答を反映し、更新後のJSON形式で注文ドラフトを返してください。"
            )
        elif source == OrderSource.LINE and current_order:
            intake_mode = "現在注文更新"
            intake_prompt = (
                "この顧客には現在注文があります。新規注文ではなく、原則として現在注文への追加・変更・取消として解釈してください。\n"
                "更新後の注文全体をJSON形式で返してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"メッセージ: {message}\n\n"
                f"まず {lookup_instruction}"
                "会話履歴と現在注文を踏まえて、更新後の注文全体を返してください。"
            )
        else:
            intake_mode = "新規注文"
            intake_prompt = (
                f"以下の注文メッセージを処理してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"メッセージ: {message}\n\n"
                f"まず {lookup_instruction}"
                f"次に注文内容を解析してJSON形式で注文ドラフトを返してください。"
                f"会話履歴がある場合は、直前のやり取りを踏まえて解釈してください。"
            )
        debug_log.append(f"[Intake] プロンプト種別: {intake_mode}")
        intake_text, intake_elapsed = await self._invoke_agent(intake_agent, intake_prompt)
        logger.info("Intake result: %s", intake_text[:500])
        debug_log.append(f"[Intake] Agent応答 ({len(intake_text)}文字, {intake_elapsed}s)")

        intake_draft = _apply_known_customer_to_intake(
            self._extract_json(intake_text),
            known_customer_id=known_customer_id,
            known_customer_name=known_customer_name,
        )
        if not intake_draft or not intake_draft.get("items"):
            debug_log.append("[Intake] JSON抽出失敗 → フォールバック応答")
            debug_log.append(f"[Intake] Agent生テキスト冒頭: {intake_text[:200]!r}")
            logger.warning("Intake agent returned no parseable draft; falling back to orchestrator")
            response_text = await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text=intake_text,
                exception_text=None,
                inventory_text=None,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                current_order=current_order,
                debug_log=debug_log,
            )
            result["response"] = response_text
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result
        if await _normalize_explicit_message_items_to_master_units(self._ctx, intake_draft, message, debug_log):
            intake_text = json.dumps(intake_draft, ensure_ascii=False, default=str)

        items = intake_draft.get("items", [])
        customer_id = intake_draft.get("customer_id", "")
        needs_confirmation = intake_draft.get("needs_confirmation", False)
        nc_reason = intake_draft.get("confirmation_reason") or intake_draft.get("confirmation_message", "")
        debug_log.append(
            f"[Intake] customer_id={customer_id or '未特定'}, items={len(items)}件, needs_confirmation={needs_confirmation}"
            + (f", 理由={nc_reason!r}" if needs_confirmation and nc_reason else "")
        )
        if needs_confirmation and not nc_reason:
            debug_log.append(f"[Intake] needs_confirmation=true（理由不明 - Agentの生テキスト: {intake_text[:100]!r}）")
        for it in items:
            debug_log.append(
                f"[Intake]   → {it.get('product_name', '?')} "
                f"{it.get('quantity', '?')}{it.get('unit', '?')}"
                f" (product_id={it.get('product_id', 'N/A')})"
            )

        # ── Step 2: Exception Agent ────────────────────────────────────────────
        exception_text: str | None = None
        exception_result: dict | None = None
        if items and customer_id:
            exception_agent = self._make_exception_agent(channel)
            items_summary = json.dumps(items, ensure_ascii=False)
            exception_prompt = (
                f"以下の注文ドラフトの異常検知を行ってください。\n"
                f"顧客ID: {customer_id}\n"
                f"注文アイテム: {items_summary}\n"
                f"各アイテムに対して detect_quantity_anomaly と detect_unit_anomaly を実行し、"
                f"結果をJSON形式で返してください。"
            )
            exception_text, exc_elapsed = await self._invoke_agent(exception_agent, exception_prompt)
            logger.info("Exception result: %s", exception_text[:500])
            exception_result = self._extract_json(exception_text)
            debug_log.append(
                f"[Exception] confirmation_needed="
                f"{exception_result.get('confirmation_needed') if exception_result else 'N/A'}"
                f" ({exc_elapsed}s)"
            )
        else:
            debug_log.append("[Exception] スキップ（items or customer_id なし）")

        anomaly_confirmation_needed = False
        if exception_result and exception_result.get("confirmation_needed"):
            anomaly_confirmation_needed = True
            needs_confirmation = True

        # ── Step 3: Inventory check (code-based) ─────────────────────────────
        checked_items: list[dict] = []
        inventory_needs_review = False
        inventory_shortage_response: str | None = None
        has_partial_stock = False
        has_only_out_of_stock = False
        if not needs_confirmation and not anomaly_confirmation_needed and items:
            draft_for_check = _build_draft_from_intake(intake_draft) or {}
            checked_items = await _check_draft_inventory(self._ctx, draft_for_check)
            for ci in checked_items:
                suf = "OK" if ci.get("is_sufficient") else "NG"
                debug_log.append(
                    f"[在庫]   {ci.get('product_name', '?')}: "
                    f"要求={_format_qty(ci.get('required_qty'))}{ci.get('unit', '')}, "
                    f"在庫={_format_qty(ci.get('available_qty'))}{ci.get('unit', '')} → {suf}"
                )
            out_of_stock, partial_stock = _classify_inventory_shortage(checked_items)
            if out_of_stock or partial_stock:
                inventory_needs_review = True
                inventory_shortage_response = _build_inventory_shortage_response(
                    checked_items,
                    source=source,
                )
                has_partial_stock = bool(partial_stock)
                has_only_out_of_stock = bool(out_of_stock) and not partial_stock
                if has_partial_stock:
                    needs_confirmation = True
                debug_log.append(f"[在庫] 不足あり: 在庫切れ={len(out_of_stock)}件, 部分在庫={len(partial_stock)}件")
                logger.info(
                    "Inventory shortage: out_of_stock=%d, partial=%d",
                    len(out_of_stock),
                    len(partial_stock),
                )
            else:
                debug_log.append(f"[在庫] 全品在庫OK ({len(checked_items)}件チェック)")
        elif anomaly_confirmation_needed:
            debug_log.append("[在庫] スキップ（異常検知で確認待ち）")
        elif needs_confirmation:
            debug_log.append("[在庫] スキップ（顧客確認待ち）")
        else:
            debug_log.append("[在庫] スキップ（itemsなし）")

        # ── Step 4a: Estimate delivery date ────────────────────────────────
        delivery_estimate_text: str | None = None
        estimated_delivery_date: date | None = None
        if not needs_confirmation and not inventory_needs_review:
            route = await _resolve_delivery_route_from_customer(intake_draft, self._ctx)
            lead_time = await _resolve_lead_time(intake_draft, self._ctx)
            debug_log.append(f"[配送] 入力: route={route}, lead_time={lead_time}")
            min_d, max_d = delivery_estimator.estimate(
                route,
                lead_time=lead_time,
                tenant_config=self._ctx.config,
            )
            delivery_estimate_text = delivery_estimator.format_estimate(min_d, max_d)
            estimated_delivery_date = min_d
            debug_log.append(f"[配送] 推定配送日: {delivery_estimate_text}")
        else:
            debug_log.append("[配送] 配送日推定スキップ（確認待ち or 在庫不足）")

        # ── Step 4b: Save order ──────────────────────────────────────────────
        saved_order: Order | None = None
        if has_only_out_of_stock:
            # 全品在庫切れ → NEEDS_REVIEWで保存（需要把握用）、配送日なし
            try:
                draft = _build_draft_from_intake(intake_draft)
                if draft:
                    oos_items = [
                        i for i in checked_items if not i.get("is_sufficient") and (i.get("available_qty") or 0) <= 0
                    ]
                    shortage_remarks = "; ".join(
                        f"{item.get('product_name', '商品')}: "
                        f"注文{_format_qty(item.get('required_qty'))}{item.get('unit', '')}, 在庫0"
                        for item in oos_items
                    )
                    saved_order = await self.create_order_from_draft(
                        draft,
                        source=source,
                        session_id=session_id,
                        existing_order=current_order if source == OrderSource.LINE and current_order else None,
                        status=OrderStatus.NEEDS_REVIEW,
                        remarks=f"在庫切れ: {shortage_remarks}" if shortage_remarks else "在庫切れのため受付不可",
                    )
                    debug_log.append(f"[保存] 要対応注文として保存: {saved_order.id}")
                    logger.info("Created review order %s (out of stock)", saved_order.id)
                    result["review_order_id"] = saved_order.id
            except Exception as exc:
                debug_log.append(f"[保存] 要対応注文の保存失敗: {exc}")
                logger.exception("Failed to save review order (out of stock)")
        elif has_partial_stock:
            debug_log.append("[保存] 部分在庫 → 顧客確認待ち、保存しない")
        elif not needs_confirmation:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if not draft:
                    debug_log.append("[保存] _build_draft_from_intake → None（ドラフト構築失敗）")
                if draft:
                    draft_items_summary = ", ".join(
                        f"{it.get('product_name', '?')} {it.get('quantity', '?')}{it.get('unit', '?')}"
                        for it in draft.get("items", [])
                    )
                    debug_log.append(
                        f"[保存] ドラフト: customer_id={draft.get('customer_id') or '未特定'}"
                        f"{'（known渡しと一致）' if draft.get('customer_id') == known_customer_id else '（known渡しと不一致 or known未渡し）'}"
                        f", items=[{draft_items_summary}]"
                    )
                    # estimated_delivery_dateを常に優先（Intake Agentが今日日付を入れる場合があるため）
                    if estimated_delivery_date:
                        draft["delivery_date"] = estimated_delivery_date
                    debug_log.append(
                        f"[保存] delivery_date={draft.get('delivery_date')}, estimated={estimated_delivery_date}"
                    )
                    saved_order = await self.create_order_from_draft(
                        draft,
                        source=source,
                        session_id=session_id,
                        existing_order=current_order if source == OrderSource.LINE and current_order else None,
                        status=OrderStatus.ACCEPTED,
                    )
                    asyncio.create_task(self._run_learning(saved_order, message))
                    debug_log.append(f"[保存] 受注確定: {saved_order.id}, delivery_date={saved_order.delivery_date}")
                    logger.info("Created order %s from single-agent pipeline", saved_order.id)
                    result["order_id"] = saved_order.id
                    result["order_saved"] = True
                    result["customer_id"] = saved_order.customer_id
                    result["current_order_id"] = saved_order.id
                    result["current_order_snapshot"] = _build_current_order_snapshot(saved_order)
                    result["current_order_editable"] = _is_order_editable(saved_order)
            except Exception as exc:
                debug_log.append(f"[保存] 受注保存失敗: {exc}")
                logger.exception("Failed to save order from single-agent pipeline")

        # ── Step 5: Generate final response ─────────────────────────────────
        if inventory_shortage_response:
            debug_log.append("[応答] 在庫不足テンプレート返答")
            response_text = inventory_shortage_response
        elif source == OrderSource.LINE and needs_confirmation and intake_draft.get("confirmation_message"):
            debug_log.append("[応答] LINE単位換算確認メッセージ")
            response_text = intake_draft["confirmation_message"]
        elif source == OrderSource.EMAIL and not needs_confirmation and intake_draft:
            debug_log.append("[応答] メール受注確定テンプレート")
            response_text = _build_email_from_template(
                "メール返信_受注確定.txt",
                intake_draft,
                delivery_estimate=delivery_estimate_text,
            )
            if saved_order:
                response_text = response_text.replace(
                    "ご注文を承りました。",
                    f"ご注文を承りました。（受注No: {saved_order.id}）",
                )
        elif source == OrderSource.EMAIL and needs_confirmation and intake_draft:
            debug_log.append("[応答] メール異常時テンプレート（LLM生成本文）")
            agent_body = await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=None,
                source=OrderSource.LINE,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                processing_note=_build_processing_note(needs_confirmation, False),
                delivery_estimate=delivery_estimate_text,
                current_order=current_order,
                debug_log=debug_log,
            )
            response_text = _build_email_from_template(
                "メール返信_異常時.txt",
                intake_draft,
                body=agent_body,
            )
        else:
            debug_log.append("[応答] LLM生成（_generate_final_response）")
            response_text = await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=None,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                processing_note=_build_processing_note(needs_confirmation, False),
                delivery_estimate=delivery_estimate_text,
                current_order=current_order,
                debug_log=debug_log,
            )
        if not inventory_shortage_response:
            if source == OrderSource.LINE and saved_order and not needs_confirmation:
                template_name = "order_update_confirm.txt" if current_order else "order_confirm.txt"
                debug_log.append(f"[応答] LINEテンプレート上書き: {template_name}")
                response_text = _build_line_from_template(
                    template_name,
                    items=saved_order.items,
                    delivery_estimate=delivery_estimate_text,
                    time_slot=saved_order.delivery_time_slot,
                )
            elif source == OrderSource.PHONE and saved_order:
                debug_log.append("[応答] 電話応答に受注No挿入")
                response_text = _insert_order_id(response_text, saved_order.id)
        debug_log.append(f"[応答] 最終応答 ({len(response_text)}文字)")
        result["response"] = response_text

        # ── Step 6: Send response ─────────────────────────────────────────────
        if response_callback:
            await response_callback(response_text)
        else:
            await self._send_line_message(response_text, reply_token, line_user_id)

        if needs_confirmation:
            debug_log.append("[セッション] 確認待ち → awaiting_reply")
            result["session_status"] = "awaiting_reply"
            draft = _build_draft_from_intake(intake_draft)
            if has_partial_stock and draft:
                draft["inventory_checked"] = checked_items
            result["pending_order_draft"] = draft
        else:
            debug_log.append("[セッション] 確認不要 → 完了")

        return result

    async def _run_multi_agent_chain(
        self,
        message: str,
        line_user_id: str,
        reply_token: str | None,
        source: OrderSource,
        response_callback: Callable[[str], Awaitable[None]] | None,
        conversation_history: list[MessageHistory] | None,
        pending_order_draft: dict | None,
        session_id: str | None,
        known_customer_id: str | None = None,
        known_customer_name: str | None = None,
        current_order: Order | None = None,
    ) -> dict:
        """新ロジック: 4つの専門Agentを順番に呼び出すパイプライン."""
        result: dict = {}
        debug_log: list[str] = []
        result["debug_log"] = debug_log
        self._ctx._debug_log = debug_log
        channel = _source_to_channel(source)

        if known_customer_id and known_customer_name:
            lookup_instruction = (
                f"顧客は特定済みです（customer_id={known_customer_id}, "
                f"customer_name={known_customer_name}）。顧客検索は不要です。"
            )
            user_label = f"メールアドレス: {line_user_id}"
            debug_log.append(
                f"[顧客解決] 経路=known渡し → Agentに顧客特定済みとして渡す: {known_customer_id} ({known_customer_name})"
            )
        elif source == OrderSource.PHONE:
            lookup_instruction = "lookup_customer でこの顧客を電話番号から特定し、"
            user_label = f"電話番号: {line_user_id}"
            debug_log.append(f"[顧客解決] 経路=電話番号lookup → Agent内で解決: {line_user_id}")
        elif source == OrderSource.EMAIL:
            lookup_instruction = "lookup_customer でこの顧客をメールアドレスから特定し、"
            user_label = f"メールアドレス: {line_user_id}"
            debug_log.append(f"[顧客解決] 経路=メールlookup → Agent内で解決: {line_user_id}")
        else:
            lookup_instruction = "lookup_customer_by_line_id でこの顧客を特定し、"
            user_label = f"LINE User ID: {line_user_id}"
            debug_log.append(f"[顧客解決] 経路=LINE User ID lookup → Agent内で解決: {line_user_id}")

        memory_ctx = _format_memory_context(conversation_history, pending_order_draft, current_order)
        debug_log.append(
            f"[コンテキスト] 履歴={len(conversation_history) if conversation_history else 0}件, "
            f"memory_ctx={len(memory_ctx)}文字"
        )

        # ── Chain Step 1: Intake Agent ─────────────────────────────────────────
        intake_agent = self._make_intake_agent(channel)
        if pending_order_draft:
            intake_mode = "ドラフト反映"
            intake_prompt = (
                f"以下は確認質問への顧客の回答です。確認待ち注文ドラフトに回答内容を反映してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"顧客の回答: {message}\n\n"
                f"まず {lookup_instruction}"
                f"次にドラフトに回答を反映し、更新後のJSON形式で注文ドラフトを返してください。"
            )
        elif source == OrderSource.LINE and current_order:
            intake_mode = "現在注文更新"
            intake_prompt = (
                "この顧客には現在注文があります。新規注文ではなく、原則として現在注文への追加・変更・取消として解釈してください。\n"
                "更新後の注文全体をJSON形式で返してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"メッセージ: {message}\n\n"
                f"まず {lookup_instruction}"
                "会話履歴と現在注文を踏まえて、更新後の注文全体を返してください。"
            )
        else:
            intake_mode = "新規注文"
            intake_prompt = (
                f"以下の注文メッセージを処理してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"メッセージ: {message}\n\n"
                f"まず {lookup_instruction}"
                f"次に注文内容を解析してJSON形式で注文ドラフトを返してください。"
                f"会話履歴がある場合は、直前のやり取りを踏まえて解釈してください。"
            )
        debug_log.append(f"[Intake] プロンプト種別: {intake_mode}")
        intake_text, intake_elapsed = await self._invoke_agent(intake_agent, intake_prompt)
        logger.info("[multi-agent] Intake result: %s", intake_text[:500])
        debug_log.append(f"[Intake] Agent応答 ({len(intake_text)}文字, {intake_elapsed}s)")

        intake_draft = _apply_known_customer_to_intake(
            self._extract_json(intake_text),
            known_customer_id=known_customer_id,
            known_customer_name=known_customer_name,
        )
        if not intake_draft or not intake_draft.get("items"):
            debug_log.append("[Intake] JSON抽出失敗 → Communication Agentフォールバック")
            debug_log.append(f"[Intake] Agent生テキスト冒頭: {intake_text[:200]!r}")
            logger.warning("[multi-agent] Intake returned no parseable draft; using Communication Agent for reply")
            response_text = await self._communication_agent_reply(
                message=message,
                line_user_id=line_user_id,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                intake_text=intake_text,
                current_order=current_order,
                debug_log=debug_log,
            )
            result["response"] = response_text
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result
        if await _normalize_explicit_message_items_to_master_units(self._ctx, intake_draft, message, debug_log):
            intake_text = json.dumps(intake_draft, ensure_ascii=False, default=str)

        items = intake_draft.get("items", [])
        customer_id = intake_draft.get("customer_id", "")
        needs_confirmation = intake_draft.get("needs_confirmation", False)
        nc_reason = intake_draft.get("confirmation_reason") or intake_draft.get("confirmation_message", "")
        debug_log.append(
            f"[Intake] customer_id={customer_id or '未特定'}, items={len(items)}件, needs_confirmation={needs_confirmation}"
            + (f", 理由={nc_reason!r}" if needs_confirmation and nc_reason else "")
        )
        if needs_confirmation and not nc_reason:
            debug_log.append(f"[Intake] needs_confirmation=true（理由不明 - Agentの生テキスト: {intake_text[:100]!r}）")
        for it in items:
            debug_log.append(
                f"[Intake]   → {it.get('product_name', '?')} "
                f"{it.get('quantity', '?')}{it.get('unit', '?')}"
                f" (product_id={it.get('product_id', 'N/A')})"
            )

        # ── Chain Step 2: Exception Agent ──────────────────────────────────────
        exception_text: str | None = None
        exception_result: dict | None = None
        anomaly_confirmation_needed = False
        if items and customer_id:
            exception_agent = self._make_exception_agent(channel)
            items_summary = json.dumps(items, ensure_ascii=False)
            exception_prompt = (
                f"以下の注文ドラフトの異常検知を行ってください。\n"
                f"顧客ID: {customer_id}\n"
                f"注文アイテム: {items_summary}\n"
                f"各アイテムに対して detect_quantity_anomaly と detect_unit_anomaly を実行し、"
                f"結果をJSON形式で返してください。"
            )
            exception_text, exc_elapsed = await self._invoke_agent(exception_agent, exception_prompt)
            logger.info("[multi-agent] Exception result: %s", exception_text[:500])
            exception_result = self._extract_json(exception_text)
            debug_log.append(
                f"[Exception] confirmation_needed="
                f"{exception_result.get('confirmation_needed') if exception_result else 'N/A'}"
                f" ({exc_elapsed}s)"
            )
            if exception_result and exception_result.get("confirmation_needed"):
                anomaly_confirmation_needed = True
                needs_confirmation = True
        else:
            debug_log.append("[Exception] スキップ（items or customer_id なし）")

        # ── Chain Step 3: Inventory check (code-based) ────────────────────────
        checked_items: list[dict] = []
        inventory_needs_review = False
        inventory_shortage_response: str | None = None
        has_partial_stock = False
        has_only_out_of_stock = False
        if not needs_confirmation and not anomaly_confirmation_needed and items:
            draft_for_check = _build_draft_from_intake(intake_draft) or {}
            checked_items = await _check_draft_inventory(self._ctx, draft_for_check)
            for ci in checked_items:
                suf = "OK" if ci.get("is_sufficient") else "NG"
                debug_log.append(
                    f"[在庫]   {ci.get('product_name', '?')}: "
                    f"要求={_format_qty(ci.get('required_qty'))}{ci.get('unit', '')}, "
                    f"在庫={_format_qty(ci.get('available_qty'))}{ci.get('unit', '')} → {suf}"
                )
            out_of_stock, partial_stock = _classify_inventory_shortage(checked_items)
            if out_of_stock or partial_stock:
                inventory_needs_review = True
                inventory_shortage_response = _build_inventory_shortage_response(
                    checked_items,
                    source=source,
                )
                has_partial_stock = bool(partial_stock)
                has_only_out_of_stock = bool(out_of_stock) and not partial_stock
                if has_partial_stock:
                    needs_confirmation = True
                debug_log.append(f"[在庫] 不足あり: 在庫切れ={len(out_of_stock)}件, 部分在庫={len(partial_stock)}件")
                logger.info(
                    "[multi-agent] Inventory shortage: out_of_stock=%d, partial=%d",
                    len(out_of_stock),
                    len(partial_stock),
                )
            else:
                debug_log.append(f"[在庫] 全品在庫OK ({len(checked_items)}件チェック)")
        elif anomaly_confirmation_needed:
            debug_log.append("[在庫] スキップ（異常検知で確認待ち）")
        elif needs_confirmation:
            debug_log.append("[在庫] スキップ（顧客確認待ち）")
        else:
            debug_log.append("[在庫] スキップ（itemsなし）")

        # ── 配送予定日推定 ────────────────────────────────────────────────────
        delivery_estimate_text: str | None = None
        estimated_delivery_date: date | None = None
        if not needs_confirmation and not inventory_needs_review:
            route = await _resolve_delivery_route_from_customer(intake_draft, self._ctx)
            lead_time = await _resolve_lead_time(intake_draft, self._ctx)
            debug_log.append(f"[配送] 入力: route={route}, lead_time={lead_time}")
            min_d, max_d = delivery_estimator.estimate(
                route,
                lead_time=lead_time,
                tenant_config=self._ctx.config,
            )
            delivery_estimate_text = delivery_estimator.format_estimate(min_d, max_d)
            estimated_delivery_date = min_d
            debug_log.append(f"[配送] 推定配送日: {delivery_estimate_text}")
        else:
            debug_log.append("[配送] 配送日推定スキップ（確認待ち or 在庫不足）")

        # ── 注文保存 ──────────────────────────────────────────────────────────
        saved_order: Order | None = None
        if has_only_out_of_stock:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if draft:
                    oos_items = [
                        i for i in checked_items if not i.get("is_sufficient") and (i.get("available_qty") or 0) <= 0
                    ]
                    shortage_remarks = "; ".join(
                        f"{item.get('product_name', '商品')}: "
                        f"注文{_format_qty(item.get('required_qty'))}{item.get('unit', '')}, 在庫0"
                        for item in oos_items
                    )
                    saved_order = await self.create_order_from_draft(
                        draft,
                        source=source,
                        session_id=session_id,
                        existing_order=current_order if source == OrderSource.LINE and current_order else None,
                        status=OrderStatus.NEEDS_REVIEW,
                        remarks=f"在庫切れ: {shortage_remarks}" if shortage_remarks else "在庫切れのため受付不可",
                    )
                    debug_log.append(f"[保存] 要対応注文として保存: {saved_order.id}")
                    logger.info("[multi-agent] Created review order %s (out of stock)", saved_order.id)
                    result["review_order_id"] = saved_order.id
            except Exception as exc:
                debug_log.append(f"[保存] 要対応注文の保存失敗: {exc}")
                logger.exception("[multi-agent] Failed to save review order (out of stock)")
        elif has_partial_stock:
            debug_log.append("[保存] 部分在庫 → 顧客確認待ち、保存しない")
        elif not needs_confirmation:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if not draft:
                    debug_log.append("[保存] _build_draft_from_intake → None（ドラフト構築失敗）")
                if draft:
                    draft_items_summary = ", ".join(
                        f"{it.get('product_name', '?')} {it.get('quantity', '?')}{it.get('unit', '?')}"
                        for it in draft.get("items", [])
                    )
                    debug_log.append(
                        f"[保存] ドラフト: customer_id={draft.get('customer_id') or '未特定'}"
                        f"{'（known渡しと一致）' if draft.get('customer_id') == known_customer_id else '（known渡しと不一致 or known未渡し）'}"
                        f", items=[{draft_items_summary}]"
                    )
                    # estimated_delivery_dateを常に優先（Intake Agentが今日日付を入れる場合があるため）
                    if estimated_delivery_date:
                        draft["delivery_date"] = estimated_delivery_date
                    debug_log.append(
                        f"[保存] delivery_date={draft.get('delivery_date')}, estimated={estimated_delivery_date}"
                    )
                    saved_order = await self.create_order_from_draft(
                        draft,
                        source=source,
                        session_id=session_id,
                        existing_order=current_order if source == OrderSource.LINE and current_order else None,
                        status=OrderStatus.ACCEPTED,
                    )
                    asyncio.create_task(self._run_learning(saved_order, message))
                    debug_log.append(f"[保存] 受注確定: {saved_order.id}, delivery_date={saved_order.delivery_date}")
                    logger.info("[multi-agent] Created order %s", saved_order.id)
                    result["order_id"] = saved_order.id
                    result["order_saved"] = True
                    result["customer_id"] = saved_order.customer_id
                    result["current_order_id"] = saved_order.id
                    result["current_order_snapshot"] = _build_current_order_snapshot(saved_order)
                    result["current_order_editable"] = _is_order_editable(saved_order)
            except Exception as exc:
                debug_log.append(f"[保存] 受注保存失敗: {exc}")
                logger.exception("[multi-agent] Failed to save order")

        # ── Chain Step 4: Communication Agent ─────────────────────────────────
        if inventory_shortage_response:
            debug_log.append("[応答] 在庫不足テンプレート返答")
            response_text = inventory_shortage_response
        elif source == OrderSource.LINE and needs_confirmation and intake_draft.get("confirmation_message"):
            debug_log.append("[応答] LINE単位換算確認メッセージ")
            response_text = intake_draft["confirmation_message"]
        elif source == OrderSource.EMAIL and not needs_confirmation and intake_draft:
            debug_log.append("[応答] メール受注確定テンプレート")
            response_text = _build_email_from_template(
                "メール返信_受注確定.txt",
                intake_draft,
                delivery_estimate=delivery_estimate_text,
            )
            if saved_order:
                response_text = response_text.replace(
                    "ご注文を承りました。",
                    f"ご注文を承りました。（受注No: {saved_order.id}）",
                )
        elif source == OrderSource.EMAIL and needs_confirmation and intake_draft:
            debug_log.append("[応答] メール異常時テンプレート（Communication Agent本文）")
            processing_note = _build_processing_note(needs_confirmation, False)
            agent_body = await self._communication_agent_reply(
                message=message,
                line_user_id=line_user_id,
                source=OrderSource.LINE,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=None,
                processing_note=processing_note,
                delivery_estimate=delivery_estimate_text,
                current_order=current_order,
                debug_log=debug_log,
            )
            response_text = _build_email_from_template(
                "メール返信_異常時.txt",
                intake_draft,
                body=agent_body,
            )
        else:
            debug_log.append("[応答] Communication Agent生成")
            processing_note = _build_processing_note(needs_confirmation, False)
            response_text = await self._communication_agent_reply(
                message=message,
                line_user_id=line_user_id,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=None,
                processing_note=processing_note,
                delivery_estimate=delivery_estimate_text,
                current_order=current_order,
                debug_log=debug_log,
            )
        if not inventory_shortage_response:
            if source == OrderSource.LINE and saved_order and not needs_confirmation:
                template_name = "order_update_confirm.txt" if current_order else "order_confirm.txt"
                debug_log.append(f"[応答] LINEテンプレート上書き: {template_name}")
                response_text = _build_line_from_template(
                    template_name,
                    items=saved_order.items,
                    delivery_estimate=delivery_estimate_text,
                    time_slot=saved_order.delivery_time_slot,
                )
            elif source == OrderSource.PHONE and saved_order:
                debug_log.append("[応答] 電話応答に受注No挿入")
                response_text = _insert_order_id(response_text, saved_order.id)
        debug_log.append(f"[応答] 最終応答 ({len(response_text)}文字)")
        result["response"] = response_text

        # ── 返信送信 ──────────────────────────────────────────────────────────
        if response_callback:
            await response_callback(response_text)
        else:
            await self._send_line_message(response_text, reply_token, line_user_id)

        if needs_confirmation:
            debug_log.append("[セッション] 確認待ち → awaiting_reply")
            result["session_status"] = "awaiting_reply"
            draft = _build_draft_from_intake(intake_draft)
            if has_partial_stock and draft:
                draft["inventory_checked"] = checked_items
            result["pending_order_draft"] = draft
        else:
            debug_log.append("[セッション] 確認不要 → 完了")

        return result

    async def _communication_agent_reply(
        self,
        message: str,
        line_user_id: str,
        source: OrderSource,
        conversation_history: list[MessageHistory] | None = None,
        pending_order_draft: dict | None = None,
        intake_text: str | None = None,
        exception_text: str | None = None,
        inventory_text: str | None = None,
        processing_note: str | None = None,
        delivery_estimate: str | None = None,
        current_order: Order | None = None,
        debug_log: list[str] | None = None,
    ) -> str:
        """Communication Agentで返信メッセージを生成する. 失敗時は既存のOrchestratorにフォールバック."""
        try:
            channel = _source_to_channel(source)
            comm_agent = self._make_communication_agent(channel)

            context_parts = [f"元のメッセージ: {message}", f"チャネル: {source.value}"]
            memory_context = _format_memory_context(conversation_history, pending_order_draft, current_order).strip()
            if memory_context:
                context_parts.append(memory_context)
            if intake_text:
                context_parts.append(f"[Intake Agent結果]\n{intake_text}")
            if exception_text:
                context_parts.append(f"[Exception Agent結果]\n{exception_text}")
            if inventory_text:
                context_parts.append(f"[Inventory Agent結果]\n{inventory_text}")
            if delivery_estimate:
                context_parts.append(f"[配送予定]\n{delivery_estimate}")
            if processing_note:
                context_parts.append(f"[処理ステータス]\n{processing_note}")
            if debug_log is not None:
                ctx_flags = []
                if memory_context:
                    ctx_flags.append("memory_ctx")
                if intake_text:
                    ctx_flags.append("intake")
                if exception_text:
                    ctx_flags.append("exception")
                if inventory_text:
                    ctx_flags.append("inventory")
                if delivery_estimate:
                    ctx_flags.append("delivery")
                if processing_note:
                    ctx_flags.append(f"note={processing_note!r}")
                debug_log.append(f"[Communication] LLM入力要素: {', '.join(ctx_flags) or 'なし'}")

            if source == OrderSource.PHONE:
                channel_instruction = "電話で読み上げるため、簡潔で自然な話し言葉にしてください。\n"
            elif source == OrderSource.EMAIL:
                channel_instruction = "メール返信本文を生成してください。丁寧で簡潔な日本語にしてください。\n"
            else:
                channel_instruction = "LINEメッセージとして簡潔に返信してください。\n"

            comm_prompt = (
                f"以下の処理結果を踏まえて、顧客への返信メッセージを生成してください。\n"
                f"{channel_instruction}"
                f"会話履歴がある場合は、前回の返信内容と矛盾しない自然な返信にしてください。\n"
                f"返信メッセージのみを出力してください（JSON不要）。\n\n" + "\n\n".join(context_parts)
            )
            response_text, comm_elapsed = await self._invoke_agent(comm_agent, comm_prompt)
            logger.info("[multi-agent] Communication Agent reply generated (%.2fs)", comm_elapsed)
            if debug_log is not None:
                debug_log.append(f"[Communication] Agent応答 ({comm_elapsed}s, {len(response_text)}文字)")

            enforced = _enforce_response_policy(
                response_text,
                needs_confirmation=processing_note is not None and "顧客確認が必要" in processing_note,
                inventory_needs_review=processing_note is not None and "在庫不足または引当不可" in processing_note,
            )
            if debug_log is not None and enforced != response_text:
                debug_log.append("[ポリシー] 応答がポリシーにより書き換えられた")
            return enforced
        except Exception:
            if debug_log is not None:
                debug_log.append("[Communication] Agent失敗 → Orchestratorフォールバック")
            logger.exception("[multi-agent] Communication Agent failed; falling back to orchestrator")
            return await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=inventory_text,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                processing_note=processing_note,
                delivery_estimate=delivery_estimate,
                current_order=current_order,
            )

    async def process_email(
        self,
        inbound: InboundMessage,
        session: OrderSession,
        reply_callback: Callable[[str, str, str | None], Awaitable[None]],
    ) -> dict:
        captured_body: list[str] = []

        async def capture_callback(body: str) -> None:
            captured_body.append(body)

        current_order = None
        if session.current_order_id:
            repo = self._ctx.get_connector("IOrderRepository")
            current_order = await repo.find_by_id(self._ctx.tenant_id, session.current_order_id)
        conversation_history = await self._list_recent_history(
            channel="email",
            channel_user_id=inbound.channel_user_id,
        )

        result = await self.process_order_message(
            message=inbound.text,
            line_user_id=inbound.channel_user_id,
            reply_token=None,
            source=OrderSource.EMAIL,
            response_callback=capture_callback,
            conversation_history=conversation_history,
            pending_order_draft=session.pending_order_draft,
            session_id=session.id,
            known_customer_id=inbound.customer_id,
            known_customer_name=inbound.customer_name,
            current_order=current_order,
        )

        if captured_body:
            order_id = result.get("order_id")
            subject = _build_email_subject(inbound.subject, order_id=order_id)
            await reply_callback(
                subject,
                captured_body[0],
                inbound.reply_to_message_id or inbound.external_message_id,
            )

        return result

    async def _list_recent_history(self, *, channel: str, channel_user_id: str) -> list[MessageHistory]:
        try:
            history_repo = self._ctx.get_connector("IMessageHistoryRepository")
            return await history_repo.list_recent_messages(
                self._ctx.tenant_id,
                channel,
                channel_user_id,
                HISTORY_CONTEXT_LIMIT,
            )
        except Exception:
            logger.exception("Failed to load %s message history; continuing without memory", channel)
            return []

    async def _generate_final_response(
        self,
        message: str,
        line_user_id: str,
        intake_text: str | None,
        exception_text: str | None,
        inventory_text: str | None,
        source: OrderSource = OrderSource.LINE,
        conversation_history: list[MessageHistory] | None = None,
        pending_order_draft: dict | None = None,
        processing_note: str | None = None,
        delivery_estimate: str | None = None,
        current_order: Order | None = None,
        debug_log: list[str] | None = None,
    ) -> str:
        channel = _source_to_channel(source)
        orchestrator_agent = self._make_orchestrator_agent(channel)
        context_parts = [
            f"元のメッセージ: {message}",
            f"LINE User ID: {line_user_id}",
        ]
        memory_context = _format_memory_context(conversation_history, pending_order_draft, current_order).strip()
        if memory_context:
            context_parts.append(memory_context)
        if intake_text:
            context_parts.append(f"[Intake Agent結果]\n{intake_text}")
        if exception_text:
            context_parts.append(f"[Exception Agent結果]\n{exception_text}")
        if inventory_text:
            context_parts.append(f"[Inventory Agent結果]\n{inventory_text}")
        if delivery_estimate:
            context_parts.append(f"[配送予定]\n{delivery_estimate}")
        if processing_note:
            context_parts.append(f"[処理ステータス]\n{processing_note}")
        if debug_log is not None:
            ctx_flags = []
            if memory_context:
                ctx_flags.append("memory_ctx")
            if intake_text:
                ctx_flags.append("intake")
            if exception_text:
                ctx_flags.append("exception")
            if inventory_text:
                ctx_flags.append("inventory")
            if delivery_estimate:
                ctx_flags.append("delivery")
            if processing_note:
                ctx_flags.append(f"note={processing_note!r}")
            debug_log.append(f"[応答生成] LLM入力要素: {', '.join(ctx_flags) or 'なし'}")

        context_instruction = (
            "会話履歴がある場合は、前回の返信内容と矛盾しない自然な返信にしてください。\n"
            "確認質問への回答を受けた場合は、回答内容を踏まえた返信にしてください。\n"
        )
        if source == OrderSource.PHONE:
            channel_instruction = (
                "以下の各Agentの処理結果を踏まえて、顧客への音声通話返信メッセージを生成してください。\n"
                "電話で読み上げるため、簡潔で自然な話し言葉にしてください。\n"
                f"{context_instruction}"
                "返信メッセージのみを出力してください（JSON不要）。\n\n"
            )
        elif source == OrderSource.EMAIL:
            channel_instruction = (
                "以下の各Agentの処理結果を踏まえて、顧客へのメール返信本文を生成してください。\n"
                "ビジネスメール形式で以下の構成にしてください:\n\n"
                "---（出力例）---\n"
                "○○様\n"
                "\n"
                "いつもお世話になっております。\n"
                "○○（会社名・レストラン名）様のご注文について、ご連絡いたします。\n"
                "\n"
                "（確認事項・異常内容などの本文）\n"
                "\n"
                "何かご不明な点がございましたら、お気軽にご連絡ください。\n"
                "よろしくお願いいたします。\n"
                "---（出力例ここまで）---\n\n"
                "ルール:\n"
                "- 宛名は Intake Agent結果の customer_name を使う\n"
                "- 挨拶の「○○様」には会社名・レストラン名を入れる\n"
                "- 各セクション間に必ず空行を1行入れる\n"
                "- 署名は出力しないこと（システムが自動付加する）\n"
                f"{context_instruction}"
                "返信本文のみを出力してください（件名やJSON不要）。\n\n"
            )
        else:
            channel_instruction = (
                "以下の各Agentの処理結果を踏まえて、顧客へのLINE返信メッセージを生成してください。\n"
                f"{context_instruction}"
                "返信メッセージのみを出力してください（JSON不要）。\n\n"
            )

        final_prompt = channel_instruction + "\n\n".join(context_parts)
        response_text, gen_elapsed = await self._invoke_agent(orchestrator_agent, final_prompt)
        logger.info("Final response generated in %.2fs", gen_elapsed)
        if debug_log is not None:
            debug_log.append(f"[応答生成] Orchestrator Agent ({gen_elapsed}s, {len(response_text)}文字)")
        enforced = _enforce_response_policy(
            response_text,
            needs_confirmation=processing_note is not None and "顧客確認が必要" in processing_note,
            inventory_needs_review=processing_note is not None and "在庫不足または引当不可" in processing_note,
        )
        if debug_log is not None and enforced != response_text:
            debug_log.append("[ポリシー] 応答がポリシーにより書き換えられた")
        return enforced

    async def _send_line_message(
        self,
        message: str,
        reply_token: str | None,
        line_user_id: str,
    ) -> None:
        comm_plugin = CommunicationPlugin(self._ctx)
        try:
            if reply_token:
                await comm_plugin.send_line_reply(reply_token=reply_token, message=message)
            else:
                await comm_plugin.send_line_push(user_id=line_user_id, message=message)
        except Exception:
            logger.exception("Failed to send LINE message")

    async def create_order_from_draft(
        self,
        draft: dict,
        source: OrderSource = OrderSource.LINE,
        session_id: str | None = None,
        status: OrderStatus = OrderStatus.ACCEPTED,
        remarks: str | None = None,
        existing_order: Order | None = None,
    ) -> Order:
        # delivery_date が文字列で渡された場合は date に変換
        raw_delivery_date = draft.get("delivery_date")
        if isinstance(raw_delivery_date, str):
            try:
                from datetime import date as _date

                draft = {**draft, "delivery_date": _date.fromisoformat(raw_delivery_date)}
            except (ValueError, AttributeError):
                draft = {**draft, "delivery_date": None}

        items = []
        for item_data in draft.get("items", []):
            items.append(
                OrderItem(
                    product_id=item_data["product_id"],
                    product_name=item_data["product_name"],
                    quantity=item_data.get("quantity"),
                    unit=item_data.get("unit", "kg"),
                    temperature_zone=TemperatureZone(item_data.get("temperature_zone", "常温")),
                )
            )

        if existing_order:
            order = existing_order.model_copy(deep=True)
            order.customer_id = draft["customer_id"]
            order.customer_name = draft.get("customer_name", order.customer_name)
            order.source = source
            order.items = items
            order.delivery_date = draft.get("delivery_date") or order.delivery_date or today_jst()
            order.delivery_route = draft.get("delivery_route") or order.delivery_route
            order.delivery_carrier = draft.get("delivery_carrier") or order.delivery_carrier
            order.delivery_time_slot = draft.get("delivery_time_slot") or order.delivery_time_slot
            order.status = status
            order.remarks = remarks if remarks is not None else order.remarks
            order.session_id = session_id or order.session_id
        else:
            order = Order(
                uid="",
                tenant_id=self._ctx.tenant_id,
                order_date=today_jst(),
                delivery_date=draft.get("delivery_date") or today_jst(),
                customer_id=draft["customer_id"],
                customer_name=draft.get("customer_name", ""),
                source=source,
                items=items,
                delivery_route=draft.get("delivery_route"),
                delivery_carrier=draft.get("delivery_carrier"),
                delivery_time_slot=draft.get("delivery_time_slot"),
                status=status,
                remarks=remarks,
                session_id=session_id,
            )

        repo = self._ctx.get_connector("IOrderRepository")
        is_existing_order = existing_order is not None
        order_id = await repo.save(order)
        order.id = order_id

        # 在庫引当（新規注文 or 更新で差分処理）
        if status == OrderStatus.ACCEPTED:
            inventory_svc = self._ctx.get_connector("IInventoryService")
            if not is_existing_order:
                # 新規注文: 全商品を引当
                for item in order.items:
                    if item.product_id and item.quantity:
                        try:
                            await inventory_svc.reserve(self._ctx.tenant_id, item.product_id, item.quantity)
                            logger.info("Reserved %s x %s for order %s", item.quantity, item.product_id, order.id)
                        except Exception:
                            logger.warning("Failed to reserve inventory for %s (order %s)", item.product_id, order.id)
            else:
                # 更新: 差分だけ引当・解除（重複引当を防ぐ）
                old_qty: dict[str, float] = {}
                if existing_order:
                    for item in existing_order.items:
                        if item.product_id:
                            old_qty[item.product_id] = old_qty.get(item.product_id, 0) + (item.quantity or 0)
                new_qty: dict[str, float] = {}
                for item in order.items:
                    if item.product_id:
                        new_qty[item.product_id] = new_qty.get(item.product_id, 0) + (item.quantity or 0)
                all_ids = set(old_qty) | set(new_qty)
                for pid in all_ids:
                    diff = new_qty.get(pid, 0) - old_qty.get(pid, 0)
                    if diff > 0:
                        try:
                            await inventory_svc.reserve(self._ctx.tenant_id, pid, diff)
                            logger.info("Reserved diff +%s x %s for order %s", diff, pid, order.id)
                        except Exception:
                            logger.warning("Failed to reserve diff for %s (order %s)", pid, order.id)
                    elif diff < 0:
                        try:
                            await inventory_svc.release(self._ctx.tenant_id, pid, abs(diff))
                            logger.info("Released diff %s x %s for order %s", abs(diff), pid, order.id)
                        except Exception:
                            logger.warning("Failed to release diff for %s (order %s)", pid, order.id)

        await dashboard_event_broker.publish(
            "order_updated" if is_existing_order else "order_created",
            self._ctx.tenant_id,
            {
                "order_id": order.id,
                "customer_id": order.customer_id,
                "customer_name": order.customer_name,
                "source": order.source.value,
                "status": order.status.value,
                "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
                "order_date": order.order_date.isoformat(),
            },
        )
        return order

    async def _run_learning(self, order: Order, original_message: str) -> None:
        try:
            from src.services.learning_service import LearningService

            learning_service = LearningService(self._ctx)
            resolved_items = [
                ResolvedItem(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    qty=item.quantity,
                    unit=item.unit,
                )
                for item in order.items
            ]
            await learning_service.record_pattern(
                customer_id=order.customer_id,
                input_expression=original_message,
                resolved_items=resolved_items,
            )
            for item in order.items:
                await learning_service.update_customer_profile(
                    customer_id=order.customer_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit=item.unit,
                )
            logger.info("Learning completed for order %s", order.id)
        except Exception:
            logger.exception("Learning failed for order %s — order flow unaffected", order.id)

    async def _try_handle_inventory_inquiry(
        self,
        message: str,
        source: OrderSource,
        current_order: Order | None = None,
        debug_log: list[str] | None = None,
    ) -> dict | None:
        if not _is_inventory_inquiry(message):
            return None

        if debug_log is not None:
            debug_log.append("[在庫照会] 在庫問い合わせと判定")

        product_master = self._ctx.get_connector("IProductMaster")
        inventory = self._ctx.get_connector("IInventoryService")
        inquiry_items = await _extract_inventory_inquiry_items(self._ctx.tenant_id, product_master, message)

        if not inquiry_items and current_order and current_order.items:
            if debug_log is not None:
                debug_log.append("[在庫照会] 商品名抽出失敗 → 現在注文の商品で照会")
            for item in current_order.items:
                product = await product_master.get_by_id(self._ctx.tenant_id, item.product_id)
                if product:
                    inquiry_items.append({"product": product, "required_qty": item.quantity})

        if not inquiry_items:
            if debug_log is not None:
                debug_log.append("[在庫照会] 照会対象商品なし → 商品名確認を要求")
            response = _format_inventory_inquiry_response([], source=source, needs_product_clarification=True)
            return {
                "intent": "inventory_inquiry",
                "response": response,
                "inventory": [],
            }

        checked_items = []
        for item in inquiry_items:
            product = item["product"]
            required_qty = item.get("required_qty") or 0
            status = await inventory.check(self._ctx.tenant_id, product.id, required_qty)
            checked_items.append(
                {
                    "product_id": product.id,
                    "product_name": product.display_name or product.name,
                    "required_qty": required_qty,
                    "available_qty": status.available_qty,
                    "unit": status.unit,
                    "is_sufficient": status.is_sufficient,
                }
            )
            if debug_log is not None:
                suf = "OK" if status.is_sufficient else "NG"
                debug_log.append(
                    f"[在庫照会]   {product.display_name or product.name}: "
                    f"在庫={status.available_qty}{status.unit} → {suf}"
                )

        return {
            "intent": "inventory_inquiry",
            "response": _format_inventory_inquiry_response(checked_items, source=source),
            "inventory": checked_items,
        }

    async def _try_create_order_from_message(
        self,
        message: str,
        line_user_id: str,
        source: OrderSource,
    ) -> Order | None:
        try:
            draft = await self._build_order_draft(message, line_user_id)
            if not draft:
                return None
            order = await self.create_order_from_draft(draft, source=source)
            logger.info("Created order %s from LINE message", order.id)
            return order
        except Exception:
            logger.exception("Failed to create order from LINE message")
            return None

    async def _build_order_draft(self, message: str, line_user_id: str) -> dict | None:
        customer_repo = self._ctx.get_connector("ICustomerRepository")
        customer = await customer_repo.find_by_line_user_id(self._ctx.tenant_id, line_user_id)
        if not customer:
            return None

        product_master = self._ctx.get_connector("IProductMaster")
        items = []
        for parsed in _parse_order_items(message):
            product = await product_master.fuzzy_match(self._ctx.tenant_id, parsed["raw_name"])
            if not product:
                logger.warning("Product not found while saving order: %s", parsed["raw_name"])
                continue
            items.append(
                {
                    "product_id": product.id,
                    "product_name": product.display_name or product.name,
                    "quantity": parsed["quantity"],
                    "unit": parsed["unit"] or product.default_unit.value,
                    "temperature_zone": product.temperature_zone.value,
                }
            )

        if not items:
            return None

        preference = customer.delivery_preference
        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "items": items,
            "delivery_date": today_jst(),
            "delivery_route": preference.default_route,
            "delivery_carrier": preference.default_carrier,
            "delivery_time_slot": preference.default_time_slot,
        }


def _resolve_delivery_route(draft: dict, ctx: TenantContext) -> DeliveryRoute | None:
    """ドラフトまたは顧客情報から配送ルートを取得する."""
    route_val = draft.get("delivery_route")
    if route_val:
        try:
            return DeliveryRoute(route_val)
        except ValueError:
            pass
    return None


async def _resolve_lead_time(draft: dict, ctx: TenantContext) -> DeliveryLeadTime | None:
    """ドラフトの顧客IDから配送リードタイムを取得する。customer_idで直接検索する。"""
    customer_id = draft.get("customer_id")
    if not customer_id:
        return None
    try:
        repo = ctx.get_connector("ICustomerRepository")
        # customer_idで直接取得（find_by_identifierは名前・LINE ID・電話番号向けのため不適切）
        customer = await repo.get_by_id(ctx.tenant_id, customer_id)
        if customer and customer.delivery_lead_time:
            return customer.delivery_lead_time
        # フォールバック: find_by_identifierでも試みる
        customer = await repo.find_by_identifier(ctx.tenant_id, customer_id)
        if customer and customer.delivery_lead_time:
            return customer.delivery_lead_time
    except Exception:
        logger.debug("Could not resolve delivery_lead_time for %s", customer_id)
    return None


async def _resolve_delivery_route_from_customer(draft: dict, ctx: TenantContext) -> DeliveryRoute | None:
    """顧客マスタから配送ルートを取得する（ドラフトにない場合のフォールバック）。"""
    route_val = draft.get("delivery_route")
    if route_val:
        try:
            return DeliveryRoute(route_val)
        except ValueError:
            pass
    customer_id = draft.get("customer_id")
    if not customer_id:
        return None
    try:
        repo = ctx.get_connector("ICustomerRepository")
        customer = await repo.get_by_id(ctx.tenant_id, customer_id)
        if customer and customer.delivery_preference and customer.delivery_preference.default_route:
            return customer.delivery_preference.default_route
    except Exception:
        logger.debug("Could not resolve delivery_route for %s", customer_id)
    return None


def _build_draft_from_intake(intake_draft: dict) -> dict | None:
    if not intake_draft.get("customer_id") or not intake_draft.get("items"):
        return None
    return {
        "customer_id": intake_draft["customer_id"],
        "customer_name": intake_draft.get("customer_name", ""),
        "items": intake_draft["items"],
        "delivery_date": intake_draft.get("delivery_date") or today_jst(),
        "delivery_route": intake_draft.get("delivery_route"),
        "delivery_carrier": intake_draft.get("delivery_carrier"),
        "delivery_time_slot": intake_draft.get("delivery_time_slot"),
    }


def _apply_known_customer_to_intake(
    intake_draft: dict | None,
    *,
    known_customer_id: str | None = None,
    known_customer_name: str | None = None,
) -> dict:
    draft = dict(intake_draft or {})
    if known_customer_id and not draft.get("customer_id"):
        draft["customer_id"] = known_customer_id
    if known_customer_name and not draft.get("customer_name"):
        draft["customer_name"] = known_customer_name
    return draft


def _find_non_positive_quantity_items(draft: dict | None) -> list[dict]:
    if not draft:
        return []

    invalid_items: list[dict] = []
    for item in draft.get("items", []) or []:
        quantity = item.get("quantity")
        if quantity is None:
            continue
        try:
            if float(quantity) <= 0:
                invalid_items.append(item)
        except (TypeError, ValueError):
            invalid_items.append(item)
    return invalid_items


def _format_invalid_quantity_response(items: list[dict], *, source: OrderSource) -> str:
    names = [item.get("product_name") or item.get("product_id") or "商品" for item in items]
    target = "、".join(names)
    if source == OrderSource.PHONE:
        return f"{target}の数量が0以下になっています。数量は1以上でお願いいたします。"
    return f"{target}の数量が0以下になっています。数量は1以上で指定してください。"


def _extract_quantity_only_reply(message: str) -> tuple[float, str | None] | None:
    normalized = re.sub(r"\s+", "", _normalize_quantity_text(message))
    normalized = re.sub(r"^(じゃあ|では|それなら|なら|それでは|やっぱり)", "", normalized)
    normalized = re.sub(r"(でお願いします|お願いします|で|にします|に変更|ください|下さい|。|！|!)$", "", normalized)
    match = re.fullmatch(r"(?P<qty>\d+(?:\.\d+)?)(?P<unit>kg|キロ|箱|個|本|袋|ケース|パック|玉|枚)?", normalized)
    if not match:
        return None
    unit = _normalize_unit(match.group("unit"))
    return float(match.group("qty")), unit


def _find_single_partial_inventory_target(draft: dict) -> dict | None:
    targets = [
        item
        for item in draft.get("inventory_checked", []) or []
        if not item.get("is_sufficient") and (item.get("available_qty") or 0) > 0
    ]
    if len(targets) != 1:
        return None
    return targets[0]


def _is_usual_order_request(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message)
    return any(keyword in normalized for keyword in ("いつもの", "何時もの", "定番"))


def _is_previous_order_request(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message)
    return any(keyword in normalized for keyword in ("前と同じ", "前回と同じ", "前の注文と同じ", "この前と同じ"))


async def _check_draft_inventory(ctx: TenantContext, draft: dict) -> list[dict]:
    return await InventoryApplicationService(ctx).check_draft_availability(draft)


def _format_phone_inventory_response(
    items: list[dict],
    needs_confirmation: bool,
    confirmation_message: str | None = None,
) -> str:
    if confirmation_message:
        return confirmation_message

    if not items:
        return "すみません、ご注文の商品と数量をもう一度お願いいたします。"

    item_phrases = [
        f"{item.get('product_name', '商品')}{_format_qty(item.get('required_qty'))}{item.get('unit') or ''}"
        for item in items
    ]
    order_summary = "、".join(item_phrases)
    insufficient = [item for item in items if not item.get("is_sufficient")]

    if insufficient:
        shortage_names = "、".join(item.get("product_name", "商品") for item in insufficient)
        return f"確認です。{order_summary}ですね。{shortage_names}は在庫確認が必要なため、担当者が確認します。"

    if needs_confirmation:
        return f"確認です。{order_summary}でよろしいですか。"

    return f"{order_summary}ですね。在庫は確認できました。ご注文を受け付けます。"


def _format_qty(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return str(value or "")


def _inventory_requires_operator_review(inventory_result: dict | None) -> bool:
    if not inventory_result:
        return False

    for key in ("all_available", "all_reserved", "accepted", "reservable"):
        if inventory_result.get(key) is False:
            return True

    if inventory_result.get("alternatives"):
        return True

    for item in inventory_result.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ("available", "reserved", "reserve_success", "accepted"):
            if item.get(key) is False:
                return True
        shortage = item.get("shortage_qty") or item.get("shortage")
        if isinstance(shortage, int | float) and shortage > 0:
            return True

    return False


def _build_inventory_review_remarks(inventory_result: dict | None) -> str:
    if not inventory_result:
        return "在庫確認結果が不明のため担当者確認"

    message = inventory_result.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()[:200]

    if inventory_result.get("alternatives"):
        return "在庫不足または代替提案あり。担当者確認が必要"

    return "在庫不足または引当不可のため担当者確認"


def _classify_inventory_shortage(checked_items: list[dict]) -> tuple[list[dict], list[dict]]:
    """在庫チェック結果を「在庫0（完全欠品）」と「一部在庫あり」に分類する。"""
    out_of_stock: list[dict] = []
    partial_stock: list[dict] = []
    for item in checked_items:
        if item.get("is_sufficient"):
            continue
        available = item.get("available_qty") or 0
        if available <= 0:
            out_of_stock.append(item)
        else:
            partial_stock.append(item)
    return out_of_stock, partial_stock


def _build_inventory_shortage_response(
    checked_items: list[dict],
    *,
    source: OrderSource,
) -> str | None:
    """在庫不足時のテンプレート返答を生成する。全品在庫OKならNoneを返す。"""
    out_of_stock, partial_stock = _classify_inventory_shortage(checked_items)
    if not out_of_stock and not partial_stock:
        return None

    lines: list[str] = []

    # 在庫0の商品
    for item in out_of_stock:
        name = item.get("product_name", "商品")
        unit = item.get("unit", "")
        qty = _format_qty(item.get("required_qty"))
        lines.append(f"{name}は在庫が0{unit}のため{qty}{unit}の注文を受け付けられません。")

    # 一部在庫の商品
    for item in partial_stock:
        name = item.get("product_name", "商品")
        unit = item.get("unit", "")
        available = _format_qty(item.get("available_qty"))
        required = _format_qty(item.get("required_qty"))
        shortage = _format_qty(max((item.get("required_qty") or 0) - (item.get("available_qty") or 0), 0))
        lines.append(f"{name}は在庫が{available}{unit}です。{required}{unit}には{shortage}{unit}不足しています。")

    if partial_stock and not out_of_stock:
        # 一部在庫のみ → 部分提案
        available_parts = []
        for item in partial_stock:
            name = item.get("product_name", "商品")
            unit = item.get("unit", "")
            available = _format_qty(item.get("available_qty"))
            available_parts.append(f"{name} {available}{unit}")
        available_text = "・".join(available_parts)
        lines.append(f"{available_text}でよろしいですか？")
    elif out_of_stock and not partial_stock:
        # 完全欠品のみ
        lines.append("ご了承ください。")
    else:
        # 混在
        available_parts = []
        for item in partial_stock:
            name = item.get("product_name", "商品")
            unit = item.get("unit", "")
            available = _format_qty(item.get("available_qty"))
            available_parts.append(f"{name} {available}{unit}")
        available_text = "・".join(available_parts)
        lines.append(f"在庫がある商品は{available_text}です。こちらでよろしいですか？")

    return "\n".join(lines)


def _build_processing_note(needs_confirmation: bool, inventory_needs_review: bool) -> str | None:
    if inventory_needs_review:
        return (
            "在庫不足または引当不可のため、受注確定していません。"
            "顧客には担当者確認中であることを伝え、受注承りました・確定しましたとは言わないでください。"
        )
    if needs_confirmation:
        return (
            "顧客確認が必要なため、受注確定していません。"
            "顧客には確認質問を送り、受注承りました・確定しましたとは言わないでください。"
        )
    return None


INVENTORY_INQUIRY_KEYWORDS = (
    "在庫",
    "ざいこ",
    "残って",
    "残り",
    "ありますか",
    "ある?",
    "ある？",
    "あるの?",
    "あるの？",
    "ございますか",
    "在庫不足",
    "配送可能",
)

ORDER_REQUEST_KEYWORDS = (
    "お願い",
    "ください",
    "下さい",
    "注文",
    "発注",
    "追加",
    "納品",
    "届け",
)


def _is_inventory_inquiry(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message.lower())
    has_inventory_keyword = any(keyword in normalized for keyword in INVENTORY_INQUIRY_KEYWORDS)
    has_order_keyword = any(keyword in normalized for keyword in ORDER_REQUEST_KEYWORDS)
    return has_inventory_keyword and not has_order_keyword


async def _extract_inventory_inquiry_items(tenant_id: str, product_master: object, message: str) -> list[dict]:
    products = await product_master.list_all(tenant_id)
    parsed_items = _parse_order_items(message)
    extracted: list[dict] = []
    seen_product_ids: set[str] = set()

    for parsed in parsed_items:
        product = await product_master.fuzzy_match(tenant_id, parsed["raw_name"])
        if not product or product.id in seen_product_ids:
            continue
        seen_product_ids.add(product.id)
        extracted.append(
            {
                "product": product,
                "required_qty": parsed["quantity"],
            }
        )

    normalized_message = re.sub(r"\s+", "", message.lower())
    for product in products:
        names = [product.name, product.display_name or ""]
        names.extend(product.aliases or [])
        if product.id in seen_product_ids:
            continue
        if any(name and re.sub(r"\s+", "", name.lower()) in normalized_message for name in names):
            seen_product_ids.add(product.id)
            extracted.append({"product": product, "required_qty": 0})

    if extracted:
        return extracted

    cleaned = _clean_inventory_inquiry_product_text(message)
    if cleaned:
        product = await product_master.fuzzy_match(tenant_id, cleaned)
        if product:
            return [{"product": product, "required_qty": 0}]

    return []


def _clean_inventory_inquiry_product_text(message: str) -> str:
    cleaned = message
    for word in (
        "在庫",
        "ざいこ",
        "ありますか",
        "ある?",
        "ある？",
        "ある",
        "ございますか",
        "確認",
        "教えて",
        "ください",
        "下さい",
        "の",
        "は",
        "を",
        "って",
        "?",
        "？",
        "。",
        "、",
    ):
        cleaned = cleaned.replace(word, "")
    return cleaned.strip(" 　\t\r\n")


def _format_inventory_inquiry_response(
    items: list[dict],
    *,
    source: OrderSource,
    needs_product_clarification: bool = False,
) -> str:
    if needs_product_clarification:
        if source == OrderSource.PHONE:
            return "確認したい商品名をもう一度お願いいたします。"
        return "確認したい商品名をもう一度教えてください。"

    lines = []
    for item in items:
        product_name = item["product_name"]
        available_qty = item["available_qty"]
        unit = item["unit"]
        required_qty = item["required_qty"]
        if required_qty:
            if item["is_sufficient"]:
                lines.append(
                    f"{product_name}は在庫が{available_qty:g}{unit}あります。{required_qty:g}{unit}ご用意できます。"
                )
            elif available_qty <= 0:
                lines.append(f"{product_name}は現在在庫切れです。{required_qty:g}{unit}ご用意できません。")
            else:
                shortage = max(required_qty - available_qty, 0)
                lines.append(
                    f"{product_name}は在庫が{available_qty:g}{unit}です。"
                    f"{required_qty:g}{unit}には{shortage:g}{unit}不足しています。"
                )
        else:
            if available_qty <= 0:
                lines.append(f"{product_name}は現在在庫切れです。")
            else:
                lines.append(f"{product_name}は現在{available_qty:g}{unit}在庫があります。")

    if source == OrderSource.PHONE:
        return " ".join(lines)
    return "\n".join(lines)


FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS = (
    "受注承りました",
    "ご注文承りました",
    "注文承りました",
    "承りました",
    "受注しました",
    "注文を受け付けました",
    "受注を受け付けました",
    "確定しました",
    "受注確定",
    "注文確定",
)


def _enforce_response_policy(
    response_text: str,
    *,
    needs_confirmation: bool,
    inventory_needs_review: bool,
) -> str:
    if not (needs_confirmation or inventory_needs_review):
        return response_text

    normalized = re.sub(r"\s+", "", response_text)
    if not any(pattern in normalized for pattern in FORBIDDEN_UNCONFIRMED_RESPONSE_PATTERNS):
        return response_text

    if inventory_needs_review:
        replacement = "ご注文内容を確認しました。在庫状況の確認が必要なため、担当者が確認して折り返します。"
    else:
        replacement = (
            "ご注文内容を確認しました。数量や内容に確認が必要です。よろしければ内容をご確認のうえ返信してください。"
        )
    logger.info("[ポリシー] 応答を書き換え: %s → %s", response_text[:80], replacement[:80])
    return replacement


def _normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    normalized = unicodedata.normalize("NFKC", unit).strip()
    if normalized == "キロ":
        return "kg"
    return normalized


def _normalize_quantity_text(message: str) -> str:
    normalized = unicodedata.normalize("NFKC", message)
    replacements = {
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


async def _apply_quantity_reply_to_single_pending_item(ctx: TenantContext, draft: dict, message: str) -> dict | None:
    quantity_reply = _extract_quantity_only_reply(message)
    items = draft.get("items", []) or []
    if not quantity_reply or len(items) != 1:
        return None

    quantity, unit = quantity_reply
    updated = copy.deepcopy(draft)
    item = updated["items"][0]
    product = None
    product_id = item.get("product_id")
    if product_id:
        try:
            product_master = ctx.get_connector("IProductMaster")
            product = await product_master.get_by_id(ctx.tenant_id, product_id)
        except Exception:
            logger.debug("Could not load product while applying quantity reply: %s", product_id)
    if product:
        normalized = _normalize_item_quantity_to_master_unit(
            product=product,
            product_name=item.get("product_name") or "商品",
            requested_quantity=quantity,
            requested_unit=unit or item.get("unit"),
        )
        if normalized:
            item["quantity"] = normalized["quantity"]
            item["unit"] = normalized["unit"]
            item["requested_quantity"] = quantity
            item["requested_unit"] = unit
            if normalized.get("needs_confirmation"):
                updated["needs_confirmation"] = True
                updated["confirmation_message"] = normalized.get("confirmation_message")
        else:
            item["quantity"] = quantity
            if unit:
                item["unit"] = unit
    else:
        item["quantity"] = quantity
        if unit:
            item["unit"] = unit
    updated.pop("inventory_checked", None)
    return updated


PACKAGE_UNITS = {"箱", "個", "パック", "房", "玉", "ケース", "袋", "本", "枚"}


async def _normalize_explicit_message_items_to_master_units(
    ctx: TenantContext,
    intake_draft: dict,
    message: str,
    debug_log: list[str] | None = None,
) -> bool:
    """顧客の明示単位を読み取りつつ、内部ドラフトは商品マスタ単位へ正規化する。"""
    parsed_items = _parse_order_items(message)
    if not parsed_items or not intake_draft.get("items"):
        return False

    product_master = ctx.get_connector("IProductMaster")
    parsed_by_product_id: dict[str, list[dict]] = {}
    products_by_id: dict[str, object] = {}
    for parsed in parsed_items:
        try:
            product = await product_master.fuzzy_match(ctx.tenant_id, parsed["raw_name"])
        except Exception:
            logger.debug("Could not match explicit message item: %s", parsed["raw_name"])
            continue
        if not product:
            continue
        product_id = getattr(product, "id", None)
        if not isinstance(product_id, str):
            continue
        products_by_id[product_id] = product
        parsed_by_product_id.setdefault(product_id, []).append(parsed)

    if not parsed_by_product_id:
        return False

    changed = False
    confirmation_messages: list[str] = []
    for item in intake_draft.get("items", []) or []:
        product_id = item.get("product_id")
        candidates = parsed_by_product_id.get(product_id) or []
        if not candidates:
            continue
        parsed = candidates.pop(0)
        product = products_by_id.get(product_id)
        if not product:
            continue

        original_quantity = item.get("quantity")
        original_unit = item.get("unit")
        normalized = _normalize_item_quantity_to_master_unit(
            product=product,
            product_name=item.get("product_name") or parsed.get("raw_name") or "商品",
            requested_quantity=parsed["quantity"],
            requested_unit=parsed.get("unit") or item.get("unit"),
        )
        if not normalized:
            continue

        item["quantity"] = normalized["quantity"]
        item["unit"] = normalized["unit"]
        item["requested_quantity"] = parsed["quantity"]
        item["requested_unit"] = parsed.get("unit")
        item["requested_expression"] = (
            f"{parsed.get('raw_name', '')}{_format_qty(parsed['quantity'])}{parsed.get('unit') or ''}"
        )
        changed = changed or item.get("quantity") != original_quantity or item.get("unit") != original_unit
        if normalized.get("needs_confirmation"):
            intake_draft["needs_confirmation"] = True
            if normalized.get("confirmation_message"):
                confirmation_messages.append(normalized["confirmation_message"])
        if debug_log is not None and (item.get("quantity") != original_quantity or item.get("unit") != original_unit):
            debug_log.append(
                "[Intake補正] 顧客入力を商品マスタ単位へ正規化: "
                f"{item.get('product_name')} {original_quantity}{original_unit} -> "
                f"{item.get('quantity')}{item.get('unit')}"
            )

    if confirmation_messages:
        intake_draft["confirmation_message"] = "\n".join(confirmation_messages)
    return changed or bool(confirmation_messages)


def _normalize_item_quantity_to_master_unit(
    *,
    product: object,
    product_name: str,
    requested_quantity: float,
    requested_unit: str | None,
) -> dict | None:
    master_unit = getattr(getattr(product, "default_unit", None), "value", None) or getattr(
        product, "default_unit", None
    )
    if not isinstance(master_unit, str) or not master_unit:
        return None

    requested_unit = _normalize_unit(requested_unit) or master_unit
    unit_weight_kg = getattr(product, "unit_weight_kg", None)
    try:
        weight_kg = float(unit_weight_kg) if unit_weight_kg is not None else None
    except (TypeError, ValueError):
        weight_kg = None

    if requested_unit == master_unit:
        return {"quantity": requested_quantity, "unit": master_unit, "needs_confirmation": False}

    if master_unit == UnitType.KG.value and requested_unit in PACKAGE_UNITS and weight_kg:
        return {
            "quantity": requested_quantity * weight_kg,
            "unit": master_unit,
            "needs_confirmation": False,
        }

    confirmation = (
        f"{product_name}{_format_qty(requested_quantity)}{requested_unit}とのご注文ですが、"
        f"システム上は{_format_qty(requested_quantity)}{master_unit}として扱います。"
        "この内容でよろしいでしょうか？"
    )
    return {
        "quantity": requested_quantity,
        "unit": master_unit,
        "needs_confirmation": True,
        "confirmation_message": confirmation,
    }


def _parse_order_items(message: str) -> list[dict]:
    normalized = _normalize_quantity_text(message).replace("、", "\n").replace(",", "\n")
    normalized = re.sub(r"\s*(?:と|及び|および)\s*", "\n", normalized)
    lines = [line.strip(" ・-　\t") for line in normalized.splitlines()]

    items = []
    for line in lines:
        match = re.search(
            r"(?P<name>.+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*"
            r"(?P<unit>kg|キロ|g|箱|個|パック|房|玉|ケース|袋|本|枚)?",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        raw_name = match.group("name").strip(" ・-　\t")
        if not raw_name:
            continue
        items.append(
            {
                "raw_name": raw_name,
                "quantity": float(match.group("qty")),
                "unit": _normalize_unit(match.group("unit")),
            }
        )
    return items


def _format_memory_context(
    conversation_history: list[MessageHistory] | None,
    pending_order_draft: dict | None,
    current_order: Order | None = None,
) -> str:
    parts: list[str] = []
    if conversation_history:
        lines = []
        for history in conversation_history[-20:]:
            role = "顧客" if history.role == "user" else "AI" if history.role == "assistant" else "システム"
            text = history.text.replace("\n", " ").strip()
            if len(text) > 240:
                text = text[:237] + "..."
            lines.append(f"- {role}: {text}")
        parts.append("会話履歴:\n" + "\n".join(lines))
    if pending_order_draft:
        parts.append("確認待ち注文ドラフト:\n" + json.dumps(pending_order_draft, ensure_ascii=False, default=str))
    if current_order:
        label = "現在注文（編集可能）" if _is_order_editable(current_order) else "現在注文（ロック済み）"
        parts.append(
            label + ":\n" + json.dumps(_build_current_order_snapshot(current_order), ensure_ascii=False, default=str)
        )
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _build_current_order_snapshot(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "customer_name": order.customer_name,
        "status": order.status.value,
        "order_date": order.order_date,
        "delivery_date": order.delivery_date,
        "delivery_time_slot": order.delivery_time_slot,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit": item.unit,
                "temperature_zone": item.temperature_zone.value,
            }
            for item in order.items
        ],
    }


def _is_order_editable(order: Order | None) -> bool:
    if not order:
        return False
    return order.status in EDITABLE_ORDER_STATUSES


def _line_action_type_from_intent(intent: OrderIntent, current_order: Order | None) -> str:
    if intent == OrderIntent.FULL_CANCEL:
        return "full_cancel"
    if intent in {OrderIntent.MODIFY_CURRENT_ORDER, OrderIntent.PARTIAL_CANCEL}:
        return "update" if current_order else "no_current_order"
    return "new_order"


def _resolve_line_action_type(message: str, current_order: Order | None) -> str:
    normalized = re.sub(r"\s+", "", message)
    if _is_full_order_cancel(message):
        intent = OrderIntent.FULL_CANCEL
    elif any(keyword in normalized for keyword in ("なしで", "外して", "抜いて")):
        intent = OrderIntent.PARTIAL_CANCEL
    elif _looks_like_change_only_message(message) or (current_order and _looks_like_order_update_request(message)):
        intent = OrderIntent.MODIFY_CURRENT_ORDER
    else:
        intent = OrderIntent.NEW_ORDER
    return _line_action_type_from_intent(intent, current_order)


def _looks_like_order_update_request(message: str) -> bool:
    return _looks_like_change_only_message(message) or bool(_parse_order_items(message))


def _looks_like_change_only_message(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message)
    keywords = (
        "追加",
        "変更",
        "修正",
        "訂正",
        "キャンセル",
        "取消",
        "取り消",
        "なしで",
        "減ら",
        "増や",
        "やっぱり",
        "さっき",
        "先ほど",
        "午後便",
        "午前便",
        "明日便",
    )
    return any(keyword in normalized for keyword in keywords)


def _is_full_order_cancel(message: str) -> bool:
    return is_rule_full_cancel(message)


def _is_current_order_inquiry(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message)
    if _is_full_order_cancel(message) or _looks_like_change_only_message(message):
        return False
    keywords = (
        "今の注文",
        "現在の注文",
        "いまの注文",
        "注文状況",
        "今入ってる注文",
        "オープン注文",
        "未完了注文",
    )
    return any(keyword in normalized for keyword in keywords)


def _format_open_orders_summary(orders: list[Order]) -> str:
    grouped: dict[date | None, list[Order]] = {}
    for order in orders:
        grouped.setdefault(order.delivery_date, []).append(order)

    def _date_key(d: date | None) -> tuple[int, date]:
        return (1, date.max) if d is None else (0, d)

    lines: list[str] = []
    for delivery_date in sorted(grouped.keys(), key=_date_key):
        day_orders = grouped[delivery_date]
        # 同一商品名+単位の数量を合算
        merged: dict[str, float] = {}
        unit_map: dict[str, str] = {}
        for order in day_orders:
            for item in order.items:
                key = f"{item.product_name}|{item.unit}"
                merged[key] = merged.get(key, 0) + item.quantity
                unit_map[key] = item.unit
        if not merged:
            continue
        if delivery_date:
            lines.append(f"【{delivery_date.month}/{delivery_date.day}配送予定】")
        else:
            lines.append("【配送日未定】")
        for key, total_qty in merged.items():
            product_name = key.split("|")[0]
            unit = unit_map[key]
            qty = int(total_qty) if float(total_qty).is_integer() else total_qty
            lines.append(f"・{product_name} {qty}{unit}")
    return "\n".join(lines)


def _is_affirmative_reply(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message).lower()
    # 数値を含む返答は数量訂正の可能性があるため肯定返答とみなさない
    if re.search(r"\d", normalized):
        return False
    affirmative_words = {
        "ok",
        "ｏｋ",
        "はい",
        "それで",
        "それでok",
        "それでお願いします",
        "お願いします",
        "それでお願い",
        "大丈夫",
        "よい",
        "良い",
        "承認",
        "確定",
    }
    return normalized in affirmative_words or normalized.endswith("でお願いします")
