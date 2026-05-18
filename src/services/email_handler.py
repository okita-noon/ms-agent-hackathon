from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser

from src.agents.orchestrator import OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.inbound import InboundAttachment, InboundMessage
from src.models.session import OrderSession
from src.plugins.communication_plugin import CommunicationPlugin

logger = logging.getLogger(__name__)

EMAIL_SESSION_TIMEOUT_HOURS = 24
EMAIL_DEDUP_TTL_SECONDS = 3600


class _EmailBodyTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


class _EmailDedup:
    def __init__(self, ttl: int = EMAIL_DEDUP_TTL_SECONDS):
        self._seen: dict[str, float] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def is_duplicate(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if key in self._seen:
                return True
            self._seen[key] = now
            return False

    def _evict(self, now: float) -> None:
        expired = [k for k, ts in self._seen.items() if now - ts > self._ttl]
        for key in expired:
            del self._seen[key]


_dedup = _EmailDedup()


class EmailIngestionService:
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

    async def fetch_message(self, message_id: str) -> dict:
        logger.info("Mock fetch for email message %s", message_id)
        return {
            "id": message_id,
            "subject": "ご注文のご連絡",
            "body": "<p>いつもお世話になっております。</p><p>りんご10箱をお願いします。</p>",
            "from": {"name": "Email Customer", "address": "customer@example.com"},
            "conversationId": f"conv-{message_id}",
            "receivedDateTime": datetime.utcnow().isoformat(),
            "replyToMessageId": None,
            "attachments": [],
        }

    async def normalize_body(self, html_body: str) -> str:
        parser = _EmailBodyTextExtractor()
        parser.feed(html_body or "")
        text = parser.get_text()
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                continue
            if re.match(r"^On .+wrote:$", line, flags=re.IGNORECASE):
                break
            if line in {"--", "___"}:
                break
            if "CONFIDENTIAL" in line.upper():
                break
            lines.append(line)

        normalized = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", normalized).strip()

    async def to_inbound_message(self, raw_message: dict, tenant_id: str) -> InboundMessage:
        normalized_text = await self.normalize_body(raw_message.get("body", ""))
        attachments = [
            InboundAttachment(
                filename=item.get("filename", ""),
                content_type=item.get("content_type", "application/octet-stream"),
                size_bytes=item.get("size_bytes", 0),
                blob_url=item.get("blob_url"),
            )
            for item in raw_message.get("attachments", [])
        ]
        sender = raw_message.get("from", {}) or {}
        received_at_raw = raw_message.get("receivedDateTime")
        if isinstance(received_at_raw, str):
            received_at = datetime.fromisoformat(received_at_raw.replace("Z", "+00:00"))
        else:
            received_at = datetime.utcnow()

        return InboundMessage(
            tenant_id=tenant_id,
            channel="email",
            channel_user_id=sender.get("address", ""),
            subject=raw_message.get("subject"),
            text=normalized_text,
            raw_text=raw_message.get("body", ""),
            received_at=received_at,
            external_message_id=raw_message.get("id", ""),
            conversation_id=raw_message.get("conversationId"),
            reply_to_message_id=raw_message.get("replyToMessageId"),
            attachments=attachments,
        )

    async def process_notification(self, message_id: str, recipient_address: str) -> None:
        dedup_key = f"{self._ctx.tenant_id}:{message_id}"
        if _dedup.is_duplicate(dedup_key):
            logger.info("Skipping duplicate email notification %s", dedup_key)
            return

        logger.info("Processing email notification for %s via %s", message_id, recipient_address)
        raw_message = await self.fetch_message(message_id)
        inbound = await self.to_inbound_message(raw_message, self._ctx.tenant_id)

        customer_repo = self._ctx.get_connector("ICustomerRepository")
        session_repo = self._ctx.get_connector("ISessionRepository")

        customer = None
        if inbound.channel_user_id:
            customer = await customer_repo.find_by_email(self._ctx.tenant_id, inbound.channel_user_id)
            if customer:
                inbound.customer_id = customer.id

        session = None
        if inbound.conversation_id:
            session = await session_repo.find_by_conversation_id(self._ctx.tenant_id, inbound.conversation_id)
        if not session:
            session = await session_repo.find_active_session(self._ctx.tenant_id, "email", inbound.channel_user_id)

        if session:
            session.last_external_message_id = inbound.external_message_id
            session.last_message_at = datetime.utcnow()
            if inbound.customer_id and not session.customer_id:
                session.customer_id = inbound.customer_id
            if inbound.conversation_id and not session.conversation_id:
                session.conversation_id = inbound.conversation_id
            await session_repo.update_session(session)
        else:
            session = OrderSession(
                id=f"email-{self._ctx.tenant_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                tenant_id=self._ctx.tenant_id,
                channel="email",
                channel_user_id=inbound.channel_user_id,
                customer_id=inbound.customer_id,
                conversation_id=inbound.conversation_id,
                last_external_message_id=inbound.external_message_id,
                status="active",
                expires_at=datetime.utcnow() + timedelta(hours=EMAIL_SESSION_TIMEOUT_HOURS),
            )
            session = await session_repo.create_session(session)

        comm_plugin = CommunicationPlugin(self._ctx)

        async def reply_callback(subject: str, body: str, reply_to_message_id: str | None = None) -> None:
            await comm_plugin.send_email(
                to_address=inbound.channel_user_id,
                subject=subject,
                body=body,
                reply_to_message_id=reply_to_message_id,
            )

        result = await self._orchestrator.process_email(inbound, session, reply_callback)

        if result.get("session_status") == "awaiting_reply":
            session.status = "awaiting_reply"
            session.pending_order_draft = result.get("pending_order_draft") or session.pending_order_draft
            session.expires_at = datetime.utcnow() + timedelta(hours=EMAIL_SESSION_TIMEOUT_HOURS)
            await session_repo.update_session(session)
        elif result.get("order_id"):
            session.status = "completed"
            session.pending_order_draft = None
            await session_repo.update_session(session)
