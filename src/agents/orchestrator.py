from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from string import Template

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from src.agents.definitions import (
    COMMUNICATION_AGENT_INSTRUCTIONS,
    EXCEPTION_AGENT_INSTRUCTIONS,
    INTAKE_AGENT_INSTRUCTIONS,
    INVENTORY_AGENT_INSTRUCTIONS,
    ORCHESTRATOR_INSTRUCTIONS,
)
from src.connectors.context import TenantContext
from src.models.inbound import InboundMessage
from src.models.message_history import MessageHistory
from src.services import delivery_estimator
from src.models.customer import DeliveryLeadTime
from src.models.order import DeliveryRoute, Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.models.session import OrderSession
from src.models.intelligence import ResolvedItem
from src.plugins.communication_plugin import CommunicationPlugin
from src.plugins.exception_plugin import ExceptionPlugin
from src.plugins.intake_plugin import IntakePlugin
from src.plugins.inventory_plugin import InventoryPlugin

logger = logging.getLogger(__name__)

DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"

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

    def _make_intake_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (IntakePlugin(self._ctx), "intake"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="IntakeAgent",
            instructions=INTAKE_AGENT_INSTRUCTIONS,
        )

    def _make_exception_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (ExceptionPlugin(self._ctx), "exception"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="ExceptionAgent",
            instructions=EXCEPTION_AGENT_INSTRUCTIONS,
        )

    def _make_inventory_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (InventoryPlugin(self._ctx), "inventory"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="InventoryAgent",
            instructions=INVENTORY_AGENT_INSTRUCTIONS,
        )

    def _make_communication_agent(self) -> ChatCompletionAgent:
        kernel = self._build_kernel(
            (CommunicationPlugin(self._ctx), "communication"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="CommunicationAgent",
            instructions=COMMUNICATION_AGENT_INSTRUCTIONS,
        )

    def _make_orchestrator_agent(self) -> ChatCompletionAgent:
        # Shared kernel with all plugins for final response generation
        kernel = self._build_kernel(
            (IntakePlugin(self._ctx), "intake"),
            (InventoryPlugin(self._ctx), "inventory"),
            (ExceptionPlugin(self._ctx), "exception"),
        )
        return ChatCompletionAgent(
            kernel=kernel,
            name="Orchestrator",
            instructions=ORCHESTRATOR_INSTRUCTIONS,
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

    async def _invoke_agent(self, agent: ChatCompletionAgent, message: str) -> str:
        result_text = ""
        thread = None
        async for response in agent.invoke(messages=message, thread=thread):
            result_text = str(response.content)
            thread = response.thread
        return result_text

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
    ) -> dict:
        result: dict = {
            "response": "",
            "line_user_id": line_user_id,
            "reply_token": reply_token,
        }

        if pending_order_draft and _is_affirmative_reply(message):
            saved_order = await self.create_order_from_draft(
                pending_order_draft,
                source=source,
                session_id=session_id,
            )
            asyncio.create_task(self._run_learning(saved_order, message))
            route = _resolve_delivery_route(pending_order_draft, self._ctx)
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
            )
            result["response"] = response_text
            result["order_id"] = saved_order.id
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        inventory_inquiry_result = await self._try_handle_inventory_inquiry(message, source)
        if inventory_inquiry_result:
            response_text = inventory_inquiry_result["response"]
            result.update(inventory_inquiry_result)
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        # ── Agent処理の分岐 ───────────────────────────────────────────────────
        if self._use_multi_agent:
            logger.info("Using multi-agent chain pipeline")
            agent_result = await self._run_multi_agent_chain(
                message=message,
                line_user_id=line_user_id,
                reply_token=reply_token,
                source=source,
                response_callback=response_callback,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                session_id=session_id,
            )
        else:
            logger.info("Using single-agent pipeline")
            agent_result = await self._run_single_agent(
                message=message,
                line_user_id=line_user_id,
                reply_token=reply_token,
                source=source,
                response_callback=response_callback,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                session_id=session_id,
            )
        result.update(agent_result)
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
    ) -> dict:
        """旧ロジック: 単一Orchestrator Agentで全処理を実行する."""
        result: dict = {}

        # ── Step 1: Intake Agent ───────────────────────────────────────────────
        intake_agent = self._make_intake_agent()
        if source == OrderSource.PHONE:
            lookup_instruction = "lookup_customer でこの顧客を電話番号から特定し、"
            user_label = f"電話番号: {line_user_id}"
        elif source == OrderSource.EMAIL:
            lookup_instruction = "lookup_customer でこの顧客をメールアドレスから特定し、"
            user_label = f"メールアドレス: {line_user_id}"
        else:
            lookup_instruction = "lookup_customer_by_line_id でこの顧客を特定し、"
            user_label = f"LINE User ID: {line_user_id}"

        memory_ctx = _format_memory_context(conversation_history, pending_order_draft)
        if pending_order_draft:
            intake_prompt = (
                f"以下は確認質問への顧客の回答です。確認待ち注文ドラフトに回答内容を反映してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"顧客の回答: {message}\n\n"
                f"まず {lookup_instruction}"
                f"次にドラフトに回答を反映し、更新後のJSON形式で注文ドラフトを返してください。"
            )
        else:
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
        intake_text = await self._invoke_agent(intake_agent, intake_prompt)
        logger.info("Intake result: %s", intake_text[:500])

        intake_draft = self._extract_json(intake_text)
        if not intake_draft or not intake_draft.get("items"):
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
            )
            result["response"] = response_text
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        items = intake_draft.get("items", [])
        customer_id = intake_draft.get("customer_id", "")
        needs_confirmation = intake_draft.get("needs_confirmation", False)

        # ── Step 2: Exception Agent ────────────────────────────────────────────
        exception_text: str | None = None
        exception_result: dict | None = None
        if items and customer_id:
            exception_agent = self._make_exception_agent()
            items_summary = json.dumps(items, ensure_ascii=False)
            exception_prompt = (
                f"以下の注文ドラフトの異常検知を行ってください。\n"
                f"顧客ID: {customer_id}\n"
                f"注文アイテム: {items_summary}\n"
                f"各アイテムに対して detect_quantity_anomaly と detect_unit_anomaly を実行し、"
                f"結果をJSON形式で返してください。"
            )
            exception_text = await self._invoke_agent(exception_agent, exception_prompt)
            logger.info("Exception result: %s", exception_text[:500])
            exception_result = self._extract_json(exception_text)

        anomaly_confirmation_needed = False
        if exception_result and exception_result.get("confirmation_needed"):
            anomaly_confirmation_needed = True
            needs_confirmation = True

        # ── Step 3: Inventory Agent ────────────────────────────────────────────
        inventory_text: str | None = None
        inventory_result: dict | None = None
        inventory_needs_review = False
        if not anomaly_confirmation_needed and items:
            inventory_agent = self._make_inventory_agent()
            items_summary = json.dumps(items, ensure_ascii=False)
            inventory_prompt = (
                f"以下の注文アイテムの在庫確認と引当を行ってください。\n"
                f"注文アイテム: {items_summary}\n"
                f"各アイテムに対して check_inventory を実行し、"
                f"在庫が足りない場合は find_alternatives を検索し、"
                f"在庫が確保できたアイテムは reserve_inventory で引当を行ってください。"
                f"結果をJSON形式で返してください。"
            )
            inventory_text = await self._invoke_agent(inventory_agent, inventory_prompt)
            logger.info("Inventory result: %s", inventory_text[:500])
            inventory_result = self._extract_json(inventory_text)
            inventory_needs_review = _inventory_requires_operator_review(inventory_result)
            if inventory_needs_review:
                needs_confirmation = True

        # ── Step 4: Save order if no confirmation needed ───────────────────────
        saved_order: Order | None = None
        if inventory_needs_review:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if draft:
                    saved_order = await self.create_order_from_draft(
                        draft,
                        source=source,
                        session_id=session_id,
                        status=OrderStatus.NEEDS_REVIEW,
                        remarks=_build_inventory_review_remarks(inventory_result),
                    )
                    logger.info("Created review order %s from inventory result", saved_order.id)
                    result["review_order_id"] = saved_order.id
            except Exception:
                logger.exception("Failed to save review order from inventory result")
        elif not needs_confirmation:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if draft:
                    saved_order = await self.create_order_from_draft(draft, source=source, session_id=session_id)
                    asyncio.create_task(self._run_learning(saved_order, message))
                    logger.info("Created order %s from single-agent pipeline", saved_order.id)
                    result["order_id"] = saved_order.id
            except Exception:
                logger.exception("Failed to save order from single-agent pipeline")

        # ── Step 4.5: Estimate delivery date ─────────────────────────────────
        delivery_estimate_text: str | None = None
        if not needs_confirmation:
            route = _resolve_delivery_route(intake_draft, self._ctx)
            lead_time = await _resolve_lead_time(intake_draft, self._ctx)
            min_d, max_d = delivery_estimator.estimate(
                route,
                lead_time=lead_time,
                tenant_config=self._ctx.config,
            )
            delivery_estimate_text = delivery_estimator.format_estimate(min_d, max_d)

        # ── Step 5: Generate final response ─────────────────────────────────
        if source == OrderSource.EMAIL and not needs_confirmation and intake_draft:
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
            agent_body = await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=inventory_text,
                source=OrderSource.LINE,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                processing_note=_build_processing_note(needs_confirmation, inventory_needs_review),
                delivery_estimate=delivery_estimate_text,
            )
            response_text = _build_email_from_template(
                "メール返信_異常時.txt",
                intake_draft,
                body=agent_body,
            )
        else:
            response_text = await self._generate_final_response(
                message=message,
                line_user_id=line_user_id,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=inventory_text,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                processing_note=_build_processing_note(needs_confirmation, inventory_needs_review),
                delivery_estimate=delivery_estimate_text,
            )
        result["response"] = response_text

        # ── Step 6: Send response ─────────────────────────────────────────────
        if response_callback:
            await response_callback(response_text)
        else:
            await self._send_line_message(response_text, reply_token, line_user_id)

        if needs_confirmation:
            result["session_status"] = "awaiting_reply"
            result["pending_order_draft"] = _build_draft_from_intake(intake_draft)

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
    ) -> dict:
        """新ロジック: 4つの専門Agentを順番に呼び出すパイプライン."""
        result: dict = {}

        if source == OrderSource.PHONE:
            lookup_instruction = "lookup_customer でこの顧客を電話番号から特定し、"
            user_label = f"電話番号: {line_user_id}"
        elif source == OrderSource.EMAIL:
            lookup_instruction = "lookup_customer でこの顧客をメールアドレスから特定し、"
            user_label = f"メールアドレス: {line_user_id}"
        else:
            lookup_instruction = "lookup_customer_by_line_id でこの顧客を特定し、"
            user_label = f"LINE User ID: {line_user_id}"

        memory_ctx = _format_memory_context(conversation_history, pending_order_draft)

        # ── Chain Step 1: Intake Agent ─────────────────────────────────────────
        intake_agent = self._make_intake_agent()
        if pending_order_draft:
            intake_prompt = (
                f"以下は確認質問への顧客の回答です。確認待ち注文ドラフトに回答内容を反映してください。\n"
                f"チャネル: {source.value}\n"
                f"{user_label}\n"
                f"{memory_ctx}"
                f"顧客の回答: {message}\n\n"
                f"まず {lookup_instruction}"
                f"次にドラフトに回答を反映し、更新後のJSON形式で注文ドラフトを返してください。"
            )
        else:
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
        intake_text = await self._invoke_agent(intake_agent, intake_prompt)
        logger.info("[multi-agent] Intake result: %s", intake_text[:500])

        intake_draft = self._extract_json(intake_text)
        if not intake_draft or not intake_draft.get("items"):
            logger.warning("[multi-agent] Intake returned no parseable draft; using Communication Agent for reply")
            response_text = await self._communication_agent_reply(
                message=message,
                line_user_id=line_user_id,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                intake_text=intake_text,
            )
            result["response"] = response_text
            if response_callback:
                await response_callback(response_text)
            else:
                await self._send_line_message(response_text, reply_token, line_user_id)
            return result

        items = intake_draft.get("items", [])
        customer_id = intake_draft.get("customer_id", "")
        needs_confirmation = intake_draft.get("needs_confirmation", False)

        # ── Chain Step 2: Exception Agent ──────────────────────────────────────
        exception_text: str | None = None
        exception_result: dict | None = None
        anomaly_confirmation_needed = False
        if items and customer_id:
            exception_agent = self._make_exception_agent()
            items_summary = json.dumps(items, ensure_ascii=False)
            exception_prompt = (
                f"以下の注文ドラフトの異常検知を行ってください。\n"
                f"顧客ID: {customer_id}\n"
                f"注文アイテム: {items_summary}\n"
                f"各アイテムに対して detect_quantity_anomaly と detect_unit_anomaly を実行し、"
                f"結果をJSON形式で返してください。"
            )
            exception_text = await self._invoke_agent(exception_agent, exception_prompt)
            logger.info("[multi-agent] Exception result: %s", exception_text[:500])
            exception_result = self._extract_json(exception_text)
            if exception_result and exception_result.get("confirmation_needed"):
                anomaly_confirmation_needed = True
                needs_confirmation = True

        # ── Chain Step 3: Inventory Agent ──────────────────────────────────────
        inventory_text: str | None = None
        inventory_result: dict | None = None
        inventory_needs_review = False
        if not anomaly_confirmation_needed and items:
            inventory_agent = self._make_inventory_agent()
            items_summary = json.dumps(items, ensure_ascii=False)
            inventory_prompt = (
                f"以下の注文アイテムの在庫確認と引当を行ってください。\n"
                f"注文アイテム: {items_summary}\n"
                f"各アイテムに対して check_inventory を実行し、"
                f"在庫が足りない場合は find_alternatives を検索し、"
                f"在庫が確保できたアイテムは reserve_inventory で引当を行ってください。"
                f"結果をJSON形式で返してください。"
            )
            inventory_text = await self._invoke_agent(inventory_agent, inventory_prompt)
            logger.info("[multi-agent] Inventory result: %s", inventory_text[:500])
            inventory_result = self._extract_json(inventory_text)
            inventory_needs_review = _inventory_requires_operator_review(inventory_result)
            if inventory_needs_review:
                needs_confirmation = True

        # ── 注文保存 ──────────────────────────────────────────────────────────
        saved_order: Order | None = None
        if inventory_needs_review:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if draft:
                    saved_order = await self.create_order_from_draft(
                        draft,
                        source=source,
                        session_id=session_id,
                        status=OrderStatus.NEEDS_REVIEW,
                        remarks=_build_inventory_review_remarks(inventory_result),
                    )
                    logger.info("[multi-agent] Created review order %s", saved_order.id)
                    result["review_order_id"] = saved_order.id
            except Exception:
                logger.exception("[multi-agent] Failed to save review order")
        elif not needs_confirmation:
            try:
                draft = _build_draft_from_intake(intake_draft)
                if draft:
                    saved_order = await self.create_order_from_draft(draft, source=source, session_id=session_id)
                    asyncio.create_task(self._run_learning(saved_order, message))
                    logger.info("[multi-agent] Created order %s", saved_order.id)
                    result["order_id"] = saved_order.id
            except Exception:
                logger.exception("[multi-agent] Failed to save order")

        # ── 配送予定日推定 ────────────────────────────────────────────────────
        delivery_estimate_text: str | None = None
        if not needs_confirmation:
            route = _resolve_delivery_route(intake_draft, self._ctx)
            lead_time = await _resolve_lead_time(intake_draft, self._ctx)
            min_d, max_d = delivery_estimator.estimate(
                route,
                lead_time=lead_time,
                tenant_config=self._ctx.config,
            )
            delivery_estimate_text = delivery_estimator.format_estimate(min_d, max_d)

        # ── Chain Step 4: Communication Agent ─────────────────────────────────
        processing_note = _build_processing_note(needs_confirmation, inventory_needs_review)
        if source == OrderSource.EMAIL and not needs_confirmation and intake_draft:
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
            agent_body = await self._communication_agent_reply(
                message=message,
                line_user_id=line_user_id,
                source=OrderSource.LINE,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=inventory_text,
                processing_note=processing_note,
                delivery_estimate=delivery_estimate_text,
            )
            response_text = _build_email_from_template(
                "メール返信_異常時.txt",
                intake_draft,
                body=agent_body,
            )
        else:
            response_text = await self._communication_agent_reply(
                message=message,
                line_user_id=line_user_id,
                source=source,
                conversation_history=conversation_history,
                pending_order_draft=pending_order_draft,
                intake_text=intake_text,
                exception_text=exception_text,
                inventory_text=inventory_text,
                processing_note=processing_note,
                delivery_estimate=delivery_estimate_text,
            )
        result["response"] = response_text

        # ── 返信送信 ──────────────────────────────────────────────────────────
        if response_callback:
            await response_callback(response_text)
        else:
            await self._send_line_message(response_text, reply_token, line_user_id)

        if needs_confirmation:
            result["session_status"] = "awaiting_reply"
            result["pending_order_draft"] = _build_draft_from_intake(intake_draft)

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
    ) -> str:
        """Communication Agentで返信メッセージを生成する. 失敗時は既存のOrchestratorにフォールバック."""
        try:
            comm_agent = self._make_communication_agent()

            context_parts = [f"元のメッセージ: {message}", f"チャネル: {source.value}"]
            memory_context = _format_memory_context(conversation_history, pending_order_draft).strip()
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
            response_text = await self._invoke_agent(comm_agent, comm_prompt)
            logger.info("[multi-agent] Communication Agent reply generated")

            return _enforce_response_policy(
                response_text,
                needs_confirmation=processing_note is not None and "顧客確認が必要" in processing_note,
                inventory_needs_review=processing_note is not None and "在庫不足または引当不可" in processing_note,
            )
        except Exception:
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

        result = await self.process_order_message(
            message=inbound.text,
            line_user_id=inbound.channel_user_id,
            reply_token=None,
            source=OrderSource.EMAIL,
            response_callback=capture_callback,
            pending_order_draft=session.pending_order_draft,
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
    ) -> str:
        orchestrator_agent = self._make_orchestrator_agent()
        context_parts = [
            f"元のメッセージ: {message}",
            f"LINE User ID: {line_user_id}",
        ]
        memory_context = _format_memory_context(conversation_history, pending_order_draft).strip()
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
        response_text = await self._invoke_agent(orchestrator_agent, final_prompt)
        return _enforce_response_policy(
            response_text,
            needs_confirmation=processing_note is not None and "顧客確認が必要" in processing_note,
            inventory_needs_review=processing_note is not None and "在庫不足または引当不可" in processing_note,
        )

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
    ) -> Order:
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

        order = Order(
            uid="",
            tenant_id=self._ctx.tenant_id,
            order_date=date.today(),
            delivery_date=draft.get("delivery_date") or date.today(),
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
        order_id = await repo.save(order)
        order.id = order_id
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

    async def _try_handle_inventory_inquiry(self, message: str, source: OrderSource) -> dict | None:
        if not _is_inventory_inquiry(message):
            return None

        product_master = self._ctx.get_connector("IProductMaster")
        inventory = self._ctx.get_connector("IInventoryService")
        inquiry_items = await _extract_inventory_inquiry_items(self._ctx.tenant_id, product_master, message)

        if not inquiry_items:
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
            "delivery_date": date.today(),
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
    """ドラフトの顧客IDから配送リードタイムを取得する."""
    customer_id = draft.get("customer_id")
    if not customer_id:
        return None
    try:
        repo = ctx.get_connector("ICustomerRepository")
        customer = await repo.find_by_identifier(ctx.tenant_id, customer_id)
        if customer and customer.delivery_lead_time:
            return customer.delivery_lead_time
    except Exception:
        logger.debug("Could not resolve delivery_lead_time for %s", customer_id)
    return None


def _build_draft_from_intake(intake_draft: dict) -> dict | None:
    if not intake_draft.get("customer_id") or not intake_draft.get("items"):
        return None
    return {
        "customer_id": intake_draft["customer_id"],
        "customer_name": intake_draft.get("customer_name", ""),
        "items": intake_draft["items"],
        "delivery_date": intake_draft.get("delivery_date") or date.today(),
        "delivery_route": intake_draft.get("delivery_route"),
        "delivery_carrier": intake_draft.get("delivery_carrier"),
        "delivery_time_slot": intake_draft.get("delivery_time_slot"),
    }


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
    "ございますか",
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
            else:
                shortage = max(required_qty - available_qty, 0)
                lines.append(
                    f"{product_name}は在庫が{available_qty:g}{unit}です。"
                    f"{required_qty:g}{unit}には{shortage:g}{unit}不足しています。"
                )
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
        return "ご注文内容を確認しました。在庫状況の確認が必要なため、担当者が確認して折り返します。"
    return "ご注文内容を確認しました。数量や内容に確認が必要です。よろしければ内容をご確認のうえ返信してください。"


def _parse_order_items(message: str) -> list[dict]:
    normalized = message.replace("、", "\n").replace(",", "\n")
    normalized = re.sub(r"\s*(?:と|及び|および)\s*", "\n", normalized)
    lines = [line.strip(" ・-　\t") for line in normalized.splitlines()]

    items = []
    for line in lines:
        match = re.search(
            r"(?P<name>.+?)\s*(?P<qty>\d+(?:\.\d+)?)\s*"
            r"(?P<unit>kg|g|箱|個|パック|房|玉|ケース|袋|本|枚)?",
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
                "unit": match.group("unit"),
            }
        )
    return items


def _format_memory_context(
    conversation_history: list[MessageHistory] | None,
    pending_order_draft: dict | None,
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
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def _is_affirmative_reply(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message).lower()
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
