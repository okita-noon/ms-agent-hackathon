from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.message_history import MessageHistory
from src.services.message_history_logger import (
    build_message_history_id,
    get_message_history_repo,
    save_message,
)


def _make_message(**overrides) -> MessageHistory:
    base = dict(
        id="hist-1",
        tenant_id="T-TEST",
        session_id="sess-1",
        channel="email",
        channel_user_id="u@example.com",
        role="user",
        text="りんご10箱",
    )
    base.update(overrides)
    return MessageHistory(**base)


class TestBuildMessageHistoryId:
    def test_uses_external_id(self):
        assert build_message_history_id("user", "sess-1", "ext-9") == "hist-sess-1-user-ext-9"

    def test_falls_back_to_timestamp(self):
        result = build_message_history_id("assistant", "sess-2")
        prefix = "hist-sess-2-assistant-"
        assert result.startswith(prefix)
        assert len(result) > len(prefix)

    def test_role_makes_id_unique(self):
        user_id = build_message_history_id("user", "sess-1", "ext-1")
        assistant_id = build_message_history_id("assistant", "sess-1", "ext-1")
        assert user_id != assistant_id


class TestGetMessageHistoryRepo:
    def test_returns_connector(self):
        repo = AsyncMock()
        ctx = MagicMock()
        ctx.get_connector.return_value = repo
        assert get_message_history_repo(ctx) is repo
        ctx.get_connector.assert_called_once_with("IMessageHistoryRepository")

    def test_returns_none_when_unavailable(self):
        ctx = MagicMock()
        ctx.get_connector.side_effect = RuntimeError("connector not configured")
        assert get_message_history_repo(ctx) is None


class TestSaveMessage:
    @pytest.mark.asyncio
    async def test_calls_create_message(self):
        repo = AsyncMock()
        message = _make_message()
        await save_message(repo, message)
        repo.create_message.assert_awaited_once_with(message)

    @pytest.mark.asyncio
    async def test_none_repo_is_noop(self):
        # repo が無くても例外を出さずに何もしない
        await save_message(None, _make_message())

    @pytest.mark.asyncio
    async def test_swallows_create_message_error(self):
        repo = AsyncMock()
        repo.create_message.side_effect = RuntimeError("cosmos down")
        # 保存失敗が呼び出し側に伝播しないこと
        await save_message(repo, _make_message())
        repo.create_message.assert_awaited_once()
