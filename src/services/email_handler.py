"""
Created: 2026-05-17
Updated: 2026-05-21 23:42
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser

import httpx

from src.agents.orchestrator import OrderOrchestrator
from src.connectors.context import TenantContext
from src.models.inbound import InboundAttachment, InboundMessage
from src.models.session import OrderSession
from src.plugins.communication_plugin import CommunicationPlugin

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
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


class _GraphTokenCache:
    """テナント単位でアクセストークンをキャッシュする"""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    async def get_token(self, graph_tenant_id: str, client_id: str, client_secret: str) -> str:
        now = time.time()
        with self._lock:
            cached = self._tokens.get(graph_tenant_id)
            if cached and cached[1] > now:
                return cached[0]

        url = GRAPH_TOKEN_URL.format(tenant_id=graph_tenant_id)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        with self._lock:
            self._tokens[graph_tenant_id] = (token, now + expires_in - 60)
        return token


_token_cache = _GraphTokenCache()


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

    async def _get_graph_token(self) -> str:
        cfg = self._ctx.config
        if not cfg.graph_tenant_id or not cfg.graph_client_id or not cfg.graph_client_secret:
            raise RuntimeError("Graph API credentials not configured for tenant %s" % cfg.tenant_id)
        return await _token_cache.get_token(cfg.graph_tenant_id, cfg.graph_client_id, cfg.graph_client_secret)

    async def fetch_message(self, message_id: str) -> dict:
        token = await self._get_graph_token()
        mailbox = self._ctx.config.graph_mailbox_user_id
        url = f"{GRAPH_API_BASE}/users/{mailbox}/messages/{message_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"$select": "id,subject,body,from,conversationId,receivedDateTime,hasAttachments"},
            )
            resp.raise_for_status()
            msg = resp.json()

        body_content = msg.get("body", {}).get("content", "")
        sender = msg.get("from", {}).get("emailAddress", {})
        attachments: list[dict] = []
        if msg.get("hasAttachments"):
            att_url = f"{url}/attachments"
            async with httpx.AsyncClient() as client:
                att_resp = await client.get(att_url, headers={"Authorization": f"Bearer {token}"})
                if att_resp.status_code == 200:
                    for att in att_resp.json().get("value", []):
                        attachments.append(
                            {
                                "filename": att.get("name", ""),
                                "content_type": att.get("contentType", "application/octet-stream"),
                                "size_bytes": att.get("size", 0),
                            }
                        )

        return {
            "id": msg.get("id", message_id),
            "subject": msg.get("subject", ""),
            "body": body_content,
            "from": {"name": sender.get("name", ""), "address": sender.get("address", "")},
            "conversationId": msg.get("conversationId"),
            "receivedDateTime": msg.get("receivedDateTime"),
            "replyToMessageId": None,
            "attachments": attachments,
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

        # 自己送信メールをスキップ（無限ループ防止）
        sender_address = (raw_message.get("from", {}) or {}).get("address", "").lower()
        if sender_address and sender_address == recipient_address.lower():
            logger.info("Skipping self-sent message from %s", sender_address)
            return

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
