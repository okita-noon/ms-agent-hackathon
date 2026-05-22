from __future__ import annotations

from typing import Protocol


class IEmailService(Protocol):
    """受注確認メールなどのメール送信を担当する Connector Interface."""

    async def send_email(
        self,
        tenant_id: str,
        to_address: str,
        subject: str,
        body_html: str,
    ) -> dict:
        """メールを送信する.

        Args:
            tenant_id: テナントID
            to_address: 送信先メールアドレス
            subject: メール件名
            body_html: メール本文（HTML）

        Returns:
            {"success": True} or {"success": False, "error": "..."}
        """
        ...
