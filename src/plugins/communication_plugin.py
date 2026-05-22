from __future__ import annotations

import logging
from typing import Annotated

import httpx
from semantic_kernel.functions import kernel_function

from src.connectors.context import TenantContext

logger = logging.getLogger(__name__)


class CommunicationPlugin:
    def __init__(self, tenant_ctx: TenantContext):
        self._ctx = tenant_ctx

    @kernel_function(
        name="send_line_reply",
        description="LINE Messaging APIでメッセージを返信する（reply token使用）",
    )
    async def send_line_reply(
        self,
        reply_token: Annotated[str, "LINE reply token"],
        message: Annotated[str, "送信するメッセージ本文"],
    ) -> dict:
        token = self._ctx.config.line_channel_access_token
        if not token:
            return {"success": False, "error": "LINE access token not configured"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "replyToken": reply_token,
                    "messages": [{"type": "text", "text": message}],
                },
            )
            if resp.status_code == 200:
                return {"success": True}
            logger.error("LINE reply failed: %s %s", resp.status_code, resp.text)
            return {"success": False, "error": resp.text}

    @kernel_function(
        name="send_line_push",
        description="LINE Messaging APIでプッシュメッセージを送信する（reply tokenがない場合）",
    )
    async def send_line_push(
        self,
        user_id: Annotated[str, "LINE User ID"],
        message: Annotated[str, "送信するメッセージ本文"],
    ) -> dict:
        token = self._ctx.config.line_channel_access_token
        if not token:
            return {"success": False, "error": "LINE access token not configured"}

        async with httpx.AsyncClient() as client:
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
                return {"success": True}
            logger.error("LINE push failed: %s %s", resp.status_code, resp.text)
            return {"success": False, "error": resp.text}

    async def _get_graph_token(self) -> str:
        cfg = self._ctx.config
        if not cfg.graph_tenant_id or not cfg.graph_client_id or not cfg.graph_client_secret:
            raise RuntimeError("Graph API credentials not configured")
        from src.services.email_handler import _token_cache

        return await _token_cache.get_token(cfg.graph_tenant_id, cfg.graph_client_id, cfg.graph_client_secret)

    @kernel_function(
        name="send_email",
        description="Graph API経由でメールを顧客へ送信する",
    )
    async def send_email(
        self,
        to_address: Annotated[str, "送信先メールアドレス"],
        subject: Annotated[str, "メール件名"],
        body: Annotated[str, "メール本文"],
        reply_to_message_id: Annotated[str | None, "返信元メッセージID"] = None,
    ) -> dict:
        cfg = self._ctx.config
        if not cfg.graph_mailbox_user_id or not cfg.graph_client_id:
            logger.warning("Graph API未設定: モック送信 to=%s subject=%s", to_address, subject)
            return {"success": True, "mock": True, "to_address": to_address, "subject": subject}

        try:
            token = await self._get_graph_token()
            mailbox = cfg.graph_mailbox_user_id

            url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail"
            payload = {
                "message": {
                    "subject": subject if subject.startswith("RE:") else f"RE: {subject}",
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to_address}}],
                },
                "saveToSentItems": True,
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload,
                )
                if resp.status_code in (200, 202):
                    logger.info("Email sent: to=%s subject=%s", to_address, subject)
                    return {"success": True, "to_address": to_address, "subject": subject}
                logger.error("Graph sendMail failed: %s %s", resp.status_code, resp.text)
                return {"success": False, "error": resp.text}
        except Exception:
            logger.exception("Email send error: to=%s", to_address)
            return {"success": False, "error": "送信中にエラーが発生しました"}
