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

    @kernel_function(
        name="send_email",
        description="メールを顧客へ送信する。Phase 1 ではモック実装としてログ出力のみ行う。",
    )
    async def send_email(
        self,
        to_address: Annotated[str, "送信先メールアドレス"],
        subject: Annotated[str, "メール件名"],
        body: Annotated[str, "メール本文"],
        reply_to_message_id: Annotated[str | None, "返信元メッセージID"] = None,
    ) -> dict:
        logger.info(
            "Mock email send: to=%s subject=%s reply_to=%s body=%s",
            to_address,
            subject,
            reply_to_message_id,
            body[:500],
        )
        return {
            "success": True,
            "mock": True,
            "to_address": to_address,
            "subject": subject,
            "reply_to_message_id": reply_to_message_id,
        }
