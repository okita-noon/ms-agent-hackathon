"""会話履歴（message-history）の保存ヘルパー。LINE/メール/電話で共通利用する。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.connectors.context import TenantContext
from src.models.message_history import MessageHistory

logger = logging.getLogger(__name__)


def get_message_history_repo(ctx: TenantContext):
    """会話履歴リポジトリを取得する。未設定でも処理を止めない。"""
    try:
        return ctx.get_connector("IMessageHistoryRepository")
    except Exception:
        logger.exception("Message history connector unavailable; continuing without memory")
        return None


async def save_message(history_repo, message: MessageHistory) -> None:
    """会話メッセージを保存する。保存失敗は応答フローを止めない。"""
    if history_repo is None:
        return
    try:
        await history_repo.create_message(message)
    except Exception:
        logger.exception("Failed to save message history; reply flow will continue")


def build_message_history_id(role: str, session_id: str, external_id: str | None = None) -> str:
    source_id = external_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"hist-{session_id}-{role}-{source_id}"
