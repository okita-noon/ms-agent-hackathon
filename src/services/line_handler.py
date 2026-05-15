from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta

from src.agents.orchestrator import OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.order import OrderSource
from src.models.session import OrderSession
from src.models.tenant import TenantConfig

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_HOURS = 2


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
        hash_value = hmac.new(
            channel_secret.encode("utf-8"), body, hashlib.sha256
        ).digest()
        expected = base64.b64encode(hash_value).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, body: dict) -> list[dict]:
        results = []
        for event in body.get("events", []):
            if event.get("type") != "message":
                continue
            if event.get("message", {}).get("type") != "text":
                continue

            user_id = event["source"]["userId"]
            text = event["message"]["text"]
            reply_token = event.get("replyToken")

            result = await self._process_message(user_id, text, reply_token)
            results.append(result)

        return results

    async def _process_message(
        self, user_id: str, text: str, reply_token: str | None
    ) -> dict:
        session_repo = self._ctx.get_connector("ISessionRepository")

        session = await session_repo.find_active_session(
            self._ctx.tenant_id, "line", user_id
        )

        if session and session.status == "awaiting_reply":
            session.last_message_at = datetime.utcnow()
            await session_repo.update_session(session)
            logger.info(
                "Continuing session %s for user %s", session.id, user_id
            )
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

        result = await self._orchestrator.process_order_message(
            message=text,
            line_user_id=user_id,
            reply_token=reply_token,
            source=OrderSource.LINE,
        )

        return {
            "session_id": session.id,
            "user_id": user_id,
            "result": result,
        }
