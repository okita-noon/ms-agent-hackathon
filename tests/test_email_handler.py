"""
Created: 2026-05-25
Updated: 2026-05-25 10:01
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.email_handler import (
    ATTACHMENT_MAX_SIZE_BYTES,
    EmailIngestionService,
    _EmailDedup,
)


# ── normalize_body テスト ─────────────────────────────────────────────────────


class TestNormalizeBody:
    """メール本文正規化ロジックのテスト"""

    @pytest.fixture
    def service(self, mock_tenant_ctx):
        return EmailIngestionService(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

    @pytest.mark.asyncio
    async def test_plain_text(self, service):
        result = await service.normalize_body("りんご10箱お願いします")
        assert result == "りんご10箱お願いします"

    @pytest.mark.asyncio
    async def test_html_tags_removed(self, service):
        html = "<html><body><p>りんご10箱</p><br><p>お願いします</p></body></html>"
        result = await service.normalize_body(html)
        assert "りんご10箱" in result
        assert "お願いします" in result
        assert "<" not in result

    @pytest.mark.asyncio
    async def test_html_style_removed_and_newlines_preserved(self, service):
        html = """
        <html>
        <head>
        <style>p {margin-top:0; margin-bottom:0}</style>
        </head>
        <body>
        大丈夫<br>
        差出人: Order AI<br>
        送信日時: 2026年5月29日 22:27
        </body>
        </html>
        """
        result = await service.normalize_body(html)
        assert "margin-top" not in result
        assert "大丈夫\n差出人: Order AI\n送信日時: 2026年5月29日 22:27" in result

    @pytest.mark.asyncio
    async def test_quoted_lines_removed(self, service):
        text = "注文します\n> 前回のメッセージ\n> もう1行"
        result = await service.normalize_body(text)
        assert "注文します" in result
        assert "前回のメッセージ" not in result

    @pytest.mark.asyncio
    async def test_on_wrote_pattern(self, service):
        text = "注文内容です\nOn 2026-05-24 Tanaka wrote:\n引用テキスト"
        result = await service.normalize_body(text)
        assert "注文内容です" in result
        assert "引用テキスト" not in result

    @pytest.mark.asyncio
    async def test_original_message_separator(self, service):
        text = "本文です\n-------- Original Message --------\n転送元の内容"
        result = await service.normalize_body(text)
        assert "本文です" in result
        assert "転送元の内容" not in result

    @pytest.mark.asyncio
    async def test_from_header_in_body(self, service):
        text = "本文です\nFrom: someone@example.com\nSent: 2026-05-24"
        result = await service.normalize_body(text)
        assert "本文です" in result
        assert "someone@example.com" not in result

    @pytest.mark.asyncio
    async def test_signature_double_dash(self, service):
        text = "注文します\n--\n田中太郎\n株式会社テスト"
        result = await service.normalize_body(text)
        assert "注文します" in result
        assert "田中太郎" not in result

    @pytest.mark.asyncio
    async def test_signature_underscores(self, service):
        text = "注文します\n___\n署名部分"
        result = await service.normalize_body(text)
        assert "注文します" in result
        assert "署名部分" not in result

    @pytest.mark.asyncio
    async def test_sent_from_iphone(self, service):
        text = "りんご5箱\nSent from my iPhone"
        result = await service.normalize_body(text)
        assert "りんご5箱" in result
        assert "iPhone" not in result

    @pytest.mark.asyncio
    async def test_sent_from_android(self, service):
        text = "バナナ20kg\nSent from my Android"
        result = await service.normalize_body(text)
        assert "バナナ20kg" in result
        assert "Android" not in result

    @pytest.mark.asyncio
    async def test_confidential_disclaimer(self, service):
        text = "注文です\nThis email is CONFIDENTIAL and intended only for the recipient"
        result = await service.normalize_body(text)
        assert "注文です" in result
        assert "CONFIDENTIAL" not in result

    @pytest.mark.asyncio
    async def test_this_email_intended_only(self, service):
        text = "注文内容\nThis email is intended only for the named recipient"
        result = await service.normalize_body(text)
        assert "注文内容" in result
        assert "intended only" not in result

    @pytest.mark.asyncio
    async def test_this_message_contains(self, service):
        text = "本文\nThis message and any attachments are confidential"
        result = await service.normalize_body(text)
        assert "本文" in result
        assert "attachments are confidential" not in result

    @pytest.mark.asyncio
    async def test_disclaimer_label(self, service):
        text = "注文します\nDISCLAIMER: This communication is privileged"
        result = await service.normalize_body(text)
        assert "注文します" in result
        assert "privileged" not in result

    @pytest.mark.asyncio
    async def test_multiple_blank_lines_collapsed(self, service):
        """空行はスキップされるため、連続空行があっても結合される"""
        text = "行1\n\n\n\n\n行2"
        result = await service.normalize_body(text)
        assert result == "行1\n行2"


# ── _filter_attachments テスト ────────────────────────────────────────────────


class TestFilterAttachments:
    """添付ファイルフィルタリングのテスト"""

    @pytest.fixture
    def service(self, mock_tenant_ctx):
        return EmailIngestionService(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

    def test_normal_attachment_passes(self, service):
        attachments = [{"filename": "order.pdf", "content_type": "application/pdf", "size_bytes": 1024}]
        result = service._filter_attachments(attachments)
        assert len(result) == 1
        assert result[0].filename == "order.pdf"

    def test_oversized_attachment_blocked(self, service):
        attachments = [
            {"filename": "huge.zip", "content_type": "application/zip", "size_bytes": ATTACHMENT_MAX_SIZE_BYTES + 1}
        ]
        result = service._filter_attachments(attachments)
        assert len(result) == 0

    def test_exactly_max_size_passes(self, service):
        attachments = [
            {"filename": "exact.pdf", "content_type": "application/pdf", "size_bytes": ATTACHMENT_MAX_SIZE_BYTES}
        ]
        result = service._filter_attachments(attachments)
        assert len(result) == 1

    def test_exe_blocked(self, service):
        attachments = [{"filename": "malware.exe", "content_type": "application/octet-stream", "size_bytes": 100}]
        result = service._filter_attachments(attachments)
        assert len(result) == 0

    def test_bat_blocked(self, service):
        attachments = [{"filename": "script.bat", "content_type": "application/x-bat", "size_bytes": 50}]
        result = service._filter_attachments(attachments)
        assert len(result) == 0

    def test_ps1_blocked(self, service):
        attachments = [{"filename": "deploy.ps1", "content_type": "text/plain", "size_bytes": 200}]
        result = service._filter_attachments(attachments)
        assert len(result) == 0

    def test_case_insensitive_extension(self, service):
        attachments = [{"filename": "VIRUS.EXE", "content_type": "application/octet-stream", "size_bytes": 100}]
        result = service._filter_attachments(attachments)
        assert len(result) == 0

    def test_no_extension_passes(self, service):
        attachments = [{"filename": "README", "content_type": "text/plain", "size_bytes": 100}]
        result = service._filter_attachments(attachments)
        assert len(result) == 1

    def test_mixed_attachments(self, service):
        attachments = [
            {"filename": "order.pdf", "content_type": "application/pdf", "size_bytes": 5000},
            {"filename": "hack.exe", "content_type": "application/octet-stream", "size_bytes": 100},
            {"filename": "photo.jpg", "content_type": "image/jpeg", "size_bytes": 2_000_000},
            {"filename": "giant.zip", "content_type": "application/zip", "size_bytes": ATTACHMENT_MAX_SIZE_BYTES + 1},
        ]
        result = service._filter_attachments(attachments)
        assert len(result) == 2
        filenames = [a.filename for a in result]
        assert "order.pdf" in filenames
        assert "photo.jpg" in filenames


# ── process_notification 会話履歴テスト ───────────────────────────────────────


class TestProcessNotificationHistory:
    """メール受信時に会話履歴が保存されることを検証する"""

    @pytest.fixture
    def service(self, mock_tenant_ctx):
        return EmailIngestionService(
            tenant_ctx=mock_tenant_ctx,
            azure_openai_endpoint="https://test.openai.azure.com/",
            azure_openai_key="test-key",
        )

    @pytest.mark.asyncio
    async def test_saves_user_and_assistant_history(self, service, mock_tenant_ctx):
        raw_message = {
            "id": "email-hist-msg-001",
            "subject": "ご注文",
            "body": "りんご10箱お願いします",
            "from": {"name": "田中", "address": "tanaka@example.com"},
            "conversationId": "conv-hist-1",
            "receivedDateTime": "2026-05-25T01:00:00Z",
            "replyToMessageId": None,
            "attachments": [],
        }

        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.find_by_email.return_value = None
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_by_conversation_id.return_value = None
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")

        service._orchestrator = AsyncMock()
        service._orchestrator.process_email.return_value = {
            "response": "ご注文を承りました。",
            "order_id": "ORD-1",
        }

        with patch.object(service, "fetch_message", new_callable=AsyncMock, return_value=raw_message):
            await service.process_notification("email-hist-msg-001", "shop@example.com")

        assert history_repo.create_message.call_count == 2
        saved = [c.args[0] for c in history_repo.create_message.call_args_list]
        assert saved[0].role == "user"
        assert saved[0].channel == "email"
        assert "りんご10箱" in saved[0].text
        assert saved[1].role == "assistant"
        assert saved[1].text == "ご注文を承りました。"
        assert saved[1].metadata.get("order_id") == "ORD-1"
        # 受注が会話履歴と同じ session に紐づくよう session_id が渡される
        assert service._orchestrator.process_email.call_args.args[1].id == saved[0].session_id

    @pytest.mark.asyncio
    async def test_history_failure_does_not_block_processing(self, service, mock_tenant_ctx):
        raw_message = {
            "id": "email-hist-msg-002",
            "subject": "ご注文",
            "body": "バナナ20kgお願いします",
            "from": {"name": "佐藤", "address": "sato@example.com"},
            "conversationId": "conv-hist-2",
            "receivedDateTime": "2026-05-25T02:00:00Z",
            "replyToMessageId": None,
            "attachments": [],
        }

        customer_repo = mock_tenant_ctx.get_connector("ICustomerRepository")
        customer_repo.find_by_email.return_value = None
        session_repo = mock_tenant_ctx.get_connector("ISessionRepository")
        session_repo.find_by_conversation_id.return_value = None
        session_repo.find_active_session.return_value = None
        session_repo.create_session.side_effect = lambda s: s
        history_repo = mock_tenant_ctx.get_connector("IMessageHistoryRepository")
        history_repo.create_message.side_effect = RuntimeError("cosmos down")

        service._orchestrator = AsyncMock()
        service._orchestrator.process_email.return_value = {"response": "OK", "order_id": "ORD-2"}

        with patch.object(service, "fetch_message", new_callable=AsyncMock, return_value=raw_message):
            # 履歴保存が失敗しても受注処理は継続する（例外を送出しない）
            await service.process_notification("email-hist-msg-002", "shop@example.com")

        service._orchestrator.process_email.assert_awaited_once()


# ── _EmailDedup テスト ────────────────────────────────────────────────────────


class TestEmailDedup:
    """メール通知の重複排除テスト"""

    def test_first_message_not_duplicate(self):
        dedup = _EmailDedup(ttl=60)
        assert dedup.is_duplicate("msg-001") is False

    def test_same_message_is_duplicate(self):
        dedup = _EmailDedup(ttl=60)
        dedup.is_duplicate("msg-001")
        assert dedup.is_duplicate("msg-001") is True

    def test_different_messages_not_duplicate(self):
        dedup = _EmailDedup(ttl=60)
        dedup.is_duplicate("msg-001")
        assert dedup.is_duplicate("msg-002") is False
