from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from src.agents.orchestrator import DEFAULT_AZURE_OPENAI_DEPLOYMENT, OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.message_history import MessageHistory
from src.models.order import Order, OrderSource, OrderStatus
from src.models.session import OrderSession
from src.services.channel_locks import get_channel_user_lock

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2
DEDUP_TTL_SECONDS = 600
HISTORY_CONTEXT_LIMIT = 20


class _EventDedup:
    """In-memory TTL cache for webhook event deduplication."""

    def __init__(self, ttl: int = DEDUP_TTL_SECONDS):
        self._seen: dict[str, float] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def is_duplicate(self, event_id: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            self._evict(now)
            if event_id in self._seen:
                return True
            self._seen[event_id] = now
            return False

    def _evict(self, now: float) -> None:
        expired = [k for k, ts in self._seen.items() if now - ts > self._ttl]
        for k in expired:
            del self._seen[k]


_dedup = _EventDedup()


class LineWebhookHandler:
    def __init__(
        self,
        tenant_ctx: TenantContext,
        azure_openai_endpoint: str,
        azure_openai_key: str,
        azure_openai_deployment_name: str = DEFAULT_AZURE_OPENAI_DEPLOYMENT,
    ):
        self._ctx = tenant_ctx
        self._orchestrator = OrderOrchestrator(
            tenant_ctx=tenant_ctx,
            azure_openai_endpoint=azure_openai_endpoint,
            azure_openai_key=azure_openai_key,
            deployment_name=azure_openai_deployment_name,
        )

    def verify_signature(self, body: bytes, signature: str) -> bool:
        channel_secret = self._ctx.config.line_channel_secret
        if not channel_secret:
            logger.error("LINE channel secret not configured — rejecting webhook (fail-closed)")
            return False
        if not signature:
            return False
        hash_value = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected = base64.b64encode(hash_value).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, body: dict) -> list[dict]:
        events = [
            e
            for e in body.get("events", [])
            if e.get("type") == "message" and e.get("message", {}).get("type") == "text"
        ]

        events.sort(key=lambda e: e.get("timestamp", 0))

        results = []
        for event in events:
            webhook_event_id = event.get("webhookEventId", "")
            if webhook_event_id and await _dedup.is_duplicate(webhook_event_id):
                logger.info("Skipping duplicate event %s", webhook_event_id)
                continue

            user_id = event["source"]["userId"]
            text = event["message"]["text"]
            message_id = event["message"].get("id")
            reply_token = event.get("replyToken")
            timestamp = _line_timestamp_to_datetime(event.get("timestamp"))

            result = await self._process_message(
                user_id,
                text,
                reply_token,
                message_id=message_id,
                webhook_event_id=webhook_event_id or None,
                received_at=timestamp,
            )
            results.append(result)

        return results

    async def _process_message(
        self,
        user_id: str,
        text: str,
        reply_token: str | None,
        message_id: str | None = None,
        webhook_event_id: str | None = None,
        received_at: datetime | None = None,
    ) -> dict:
        logger.info("Processing message from %s: %s", user_id, text[:100])

        async with get_channel_user_lock("line", user_id):
            return await self._process_message_locked(
                user_id=user_id,
                text=text,
                reply_token=reply_token,
                message_id=message_id,
                webhook_event_id=webhook_event_id,
                received_at=received_at,
            )

    async def _process_message_locked(
        self,
        user_id: str,
        text: str,
        reply_token: str | None,
        message_id: str | None = None,
        webhook_event_id: str | None = None,
        received_at: datetime | None = None,
    ) -> dict:
        session_repo = self._ctx.get_connector("ISessionRepository")
        history_repo = self._get_message_history_repo()

        session = await session_repo.find_active_session(self._ctx.tenant_id, "line", user_id)

        if session and session.status == "awaiting_reply":
            session.last_message_at = datetime.now(timezone.utc)
            await session_repo.update_session(session)
            logger.info("Continuing session %s for user %s", session.id, user_id)
        elif not session:
            session = OrderSession(
                id=f"sess-{user_id[-8:]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                tenant_id=self._ctx.tenant_id,
                channel="line",
                channel_user_id=user_id,
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TIMEOUT_HOURS),
            )
            session = await session_repo.create_session(session)
            logger.info("Created new session %s for user %s", session.id, user_id)

        current_order = await self._resolve_current_order(user_id, session)
        if current_order:
            session.customer_id = current_order.customer_id
            session.current_order_id = current_order.id
            session.current_order_snapshot = _build_current_order_snapshot(current_order)
            session.current_order_editable = _is_order_editable(current_order)

        conversation_history = await self._list_recent_history(history_repo, user_id)
        await self._save_history_message(
            history_repo,
            MessageHistory(
                id=_build_message_history_id("user", session.id, webhook_event_id, message_id),
                tenant_id=self._ctx.tenant_id,
                session_id=session.id,
                channel="line",
                channel_user_id=user_id,
                role="user",
                text=text,
                message_id=message_id,
                webhook_event_id=webhook_event_id,
                created_at=received_at or datetime.now(timezone.utc),
            ),
        )

        try:
            result = await self._orchestrator.process_order_message(
                message=text,
                line_user_id=user_id,
                reply_token=reply_token,
                source=OrderSource.LINE,
                conversation_history=conversation_history,
                pending_order_draft=session.pending_order_draft,
                session_id=session.id,
                current_order=current_order,
            )
        except Exception:
            logger.exception("Agent processing failed for user %s", user_id)
            fallback_message = "ご注文を受け付けました。担当者が確認いたします。"
            await self._send_line_push(user_id, fallback_message)
            await self._save_history_message(
                history_repo,
                MessageHistory(
                    id=_build_message_history_id("assistant", session.id, webhook_event_id, None),
                    tenant_id=self._ctx.tenant_id,
                    session_id=session.id,
                    channel="line",
                    channel_user_id=user_id,
                    role="assistant",
                    text=fallback_message,
                    webhook_event_id=webhook_event_id,
                ),
            )
            return {
                "session_id": session.id,
                "user_id": user_id,
                "error": "agent_processing_failed",
            }

        response_text = result.get("response")
        if response_text:
            await self._save_history_message(
                history_repo,
                MessageHistory(
                    id=_build_message_history_id("assistant", session.id, webhook_event_id, None),
                    tenant_id=self._ctx.tenant_id,
                    session_id=session.id,
                    channel="line",
                    channel_user_id=user_id,
                    role="assistant",
                    text=response_text,
                    webhook_event_id=webhook_event_id,
                    metadata={"order_id": result.get("order_id")},
                ),
            )

        if result.get("session_status") == "awaiting_reply":
            session.status = "awaiting_reply"
            session.pending_order_draft = result.get("pending_order_draft") or session.pending_order_draft
            session.pending_action_type = result.get("pending_action_type") or session.pending_action_type
            session.customer_id = result.get("customer_id") or session.customer_id
            session.current_order_id = result.get("current_order_id") or session.current_order_id
            session.current_order_snapshot = result.get("current_order_snapshot") or session.current_order_snapshot
            session.current_order_editable = result.get("current_order_editable", session.current_order_editable)
            session.expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TIMEOUT_HOURS)
            await session_repo.update_session(session)
        elif result.get("order_id"):
            session.status = "completed"
            session.pending_order_draft = None
            session.pending_action_type = None
            session.customer_id = result.get("customer_id") or session.customer_id
            if result.get("current_order_cleared"):
                session.current_order_id = None
                session.current_order_snapshot = None
                session.current_order_editable = False
            else:
                session.current_order_id = result.get("current_order_id") or session.current_order_id
                session.current_order_snapshot = result.get("current_order_snapshot") or session.current_order_snapshot
                session.current_order_editable = result.get("current_order_editable", session.current_order_editable)
            await session_repo.update_session(session)

        return {
            "session_id": session.id,
            "user_id": user_id,
            "result": result,
        }

    def _get_message_history_repo(self):
        try:
            return self._ctx.get_connector("IMessageHistoryRepository")
        except Exception:
            logger.exception("Message history connector unavailable; continuing without LINE memory")
            return None

    async def _list_recent_history(self, history_repo, user_id: str) -> list[MessageHistory]:
        if not history_repo:
            return []
        try:
            return await history_repo.list_recent_messages(
                self._ctx.tenant_id,
                "line",
                user_id,
                HISTORY_CONTEXT_LIMIT,
            )
        except Exception:
            logger.exception("Failed to load LINE message history; continuing without memory")
            return []

    async def _save_history_message(self, history_repo, message: MessageHistory) -> None:
        if not history_repo:
            return
        try:
            await history_repo.create_message(message)
        except Exception:
            logger.exception("Failed to save LINE message history; reply flow will continue")

    async def _send_line_push(self, user_id: str, message: str) -> bool:
        token = self._ctx.config.line_channel_access_token
        if not token:
            logger.error("LINE access token not configured")
            return False

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "to": user_id,
                    "messages": [{"type": "text", "text": message}],
                },
            )
            if resp.status_code == 200:
                logger.info("LINE push sent to %s", user_id)
                return True
            logger.error("LINE push failed: %s %s", resp.status_code, resp.text)
            return False

    async def _resolve_current_order(self, user_id: str, session: OrderSession) -> Order | None:
        customer_id = session.customer_id
        customer_repo = self._ctx.get_connector("ICustomerRepository")
        if not customer_id:
            customer = await customer_repo.find_by_line_user_id(self._ctx.tenant_id, user_id)
            if customer:
                customer_id = customer.id

        if not customer_id:
            return None

        order_repo = self._ctx.get_connector("IOrderRepository")
        orders = await order_repo.list_by_customer(customer_id, limit=10)
        return _pick_current_order(orders)


def _line_timestamp_to_datetime(timestamp: int | None) -> datetime | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)


def _build_message_history_id(
    role: str,
    session_id: str,
    webhook_event_id: str | None,
    message_id: str | None,
) -> str:
    source_id = webhook_event_id or message_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"hist-{session_id}-{role}-{source_id}"


def _pick_current_order(orders: list[Order]) -> Order | None:
    open_statuses = {OrderStatus.ACCEPTED, OrderStatus.NEEDS_REVIEW, OrderStatus.SHIPPING}
    candidates = [order for order in orders if order.status in open_statuses]
    if not candidates:
        return None
    return sorted(candidates, key=lambda order: order.updated_at, reverse=True)[0]


def _is_order_editable(order: Order) -> bool:
    return order.status in {OrderStatus.ACCEPTED, OrderStatus.NEEDS_REVIEW}


def _build_current_order_snapshot(order: Order) -> dict:
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "customer_name": order.customer_name,
        "status": order.status.value,
        "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
        "delivery_time_slot": order.delivery_time_slot,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit": item.unit,
            }
            for item in order.items
        ],
    }
