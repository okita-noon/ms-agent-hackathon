from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
import threading
from datetime import datetime, timedelta

import httpx

from src.agents.orchestrator import OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.intelligence import ResolvedItem
from src.models.order import OrderSource
from src.models.session import OrderSession
from src.services.learning_service import LearningService

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2
DEDUP_TTL_SECONDS = 600


class _EventDedup:
    """In-memory TTL cache for webhook event deduplication."""

    def __init__(self, ttl: int = DEDUP_TTL_SECONDS):
        self._seen: dict[str, float] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def is_duplicate(self, event_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
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
    ):
        self._ctx = tenant_ctx
        self._orchestrator = OrderOrchestrator(
            tenant_ctx=tenant_ctx,
            azure_openai_endpoint=azure_openai_endpoint,
            azure_openai_key=azure_openai_key,
        )

    def verify_signature(self, body: bytes, signature: str) -> bool:
        channel_secret = self._ctx.config.line_channel_secret
        if not channel_secret:
            logger.warning("LINE channel secret not configured, skipping verification")
            return True
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
            if webhook_event_id and _dedup.is_duplicate(webhook_event_id):
                logger.info("Skipping duplicate event %s", webhook_event_id)
                continue

            user_id = event["source"]["userId"]
            text = event["message"]["text"]
            reply_token = event.get("replyToken")

            result = await self._process_message(user_id, text, reply_token)
            results.append(result)

        return results

    async def _process_message(self, user_id: str, text: str, reply_token: str | None) -> dict:
        logger.info("Processing message from %s: %s", user_id, text[:100])

        session_repo = self._ctx.get_connector("ISessionRepository")

        session = await session_repo.find_active_session(self._ctx.tenant_id, "line", user_id)

        if session and session.status == "awaiting_reply":
            session.last_message_at = datetime.utcnow()
            await session_repo.update_session(session)
            logger.info("Continuing session %s for user %s", session.id, user_id)
        elif not session:
            session = OrderSession(
                id=f"sess-{user_id[-8:]}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                tenant_id=self._ctx.tenant_id,
                channel="line",
                channel_user_id=user_id,
                status="active",
                expires_at=datetime.utcnow() + timedelta(hours=SESSION_TIMEOUT_HOURS),
            )
            session = await session_repo.create_session(session)
            logger.info("Created new session %s for user %s", session.id, user_id)

        try:
            result = await self._orchestrator.process_order_message(
                message=text,
                line_user_id=user_id,
                reply_token=reply_token,
                source=OrderSource.LINE,
            )
        except Exception:
            logger.exception("Agent processing failed for user %s", user_id)
            await self._send_line_push(
                user_id,
                "ご注文を受け付けました。担当者が確認いたします。",
            )
            return {
                "session_id": session.id,
                "user_id": user_id,
                "error": "agent_processing_failed",
            }

        order_id = result.get("order_id")
        if order_id:
            asyncio.create_task(self._run_learning(order_id=order_id, user_id=user_id, original_message=text))

        return {
            "session_id": session.id,
            "user_id": user_id,
            "result": result,
        }

    async def _run_learning(self, order_id: str, user_id: str, original_message: str) -> None:
        try:
            order_repo = self._ctx.get_connector("IOrderRepository")
            customer_repo = self._ctx.get_connector("ICustomerRepository")

            order = await order_repo.find_by_id(order_id)
            if not order:
                logger.warning("Learning skipped: order %s not found", order_id)
                return

            customer = await customer_repo.find_by_line_user_id(self._ctx.tenant_id, user_id)
            if not customer:
                logger.warning("Learning skipped: customer not found for LINE user %s", user_id)
                return

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
                customer_id=customer.id,
                input_expression=original_message,
                resolved_items=resolved_items,
            )

            for item in order.items:
                await learning_service.update_customer_profile(
                    customer_id=customer.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit=item.unit,
                )

            logger.info("Learning completed for order %s, customer %s", order_id, customer.id)
        except Exception:
            logger.exception(
                "Learning failed for order %s (user %s) — order flow unaffected",
                order_id,
                user_id,
            )

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
