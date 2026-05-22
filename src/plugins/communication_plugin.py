from __future__ import annotations

import logging
import os
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from typing import Annotated

import httpx
from semantic_kernel.functions import kernel_function

from src.connectors.context import TenantContext

logger = logging.getLogger(__name__)

GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
DEFAULT_GRAPH_DELEGATED_SCOPE = "https://graph.microsoft.com/Mail.Send offline_access"
DEFAULT_EXTERNAL_ROUTE_MODE = "delegated_first"
DEFAULT_EXTERNAL_FALLBACK_PROVIDER = "smtp"


class _GraphDelegatedTokenCache:
    """Cache delegated access tokens obtained from a refresh token."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0
        self._refresh_token: str | None = None
        self._lock = threading.Lock()

    async def get_token(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        scope: str = DEFAULT_GRAPH_DELEGATED_SCOPE,
    ) -> str:
        now = time.time()
        with self._lock:
            if self._token and self._expires_at > now:
                return self._token

        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": self._refresh_token or refresh_token,
            "scope": scope,
        }
        token_url = GRAPH_TOKEN_URL.format(tenant_id=tenant_id)
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()

        access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        next_refresh_token = data.get("refresh_token")
        with self._lock:
            self._token = access_token
            self._expires_at = now + max(expires_in - 60, 60)
            if next_refresh_token:
                self._refresh_token = next_refresh_token
        return access_token


_delegated_token_cache = _GraphDelegatedTokenCache()


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

    async def _get_graph_delegated_token(self) -> str:
        cfg = self._ctx.config
        direct_access_token = os.environ.get("GRAPH_DELEGATED_ACCESS_TOKEN", "").strip()
        if direct_access_token:
            return direct_access_token

        refresh_token = os.environ.get("GRAPH_DELEGATED_REFRESH_TOKEN", "").strip()
        scope = os.environ.get("GRAPH_DELEGATED_SCOPE", DEFAULT_GRAPH_DELEGATED_SCOPE).strip()
        if not cfg.graph_tenant_id or not cfg.graph_client_id or not cfg.graph_client_secret or not refresh_token:
            raise RuntimeError("Graph delegated token config is incomplete")
        return await _delegated_token_cache.get_token(
            tenant_id=cfg.graph_tenant_id,
            client_id=cfg.graph_client_id,
            client_secret=cfg.graph_client_secret,
            refresh_token=refresh_token,
            scope=scope,
        )

    @staticmethod
    def _domain_of(address: str) -> str:
        if "@" not in address:
            return ""
        return address.rsplit("@", 1)[1].strip().lower()

    def _internal_domains(self) -> set[str]:
        domains: set[str] = set()
        configured = os.environ.get("EMAIL_INTERNAL_DOMAINS", "")
        for item in configured.split(","):
            domain = item.strip().lower()
            if domain:
                domains.add(domain)

        tenant_mailbox = (self._ctx.config.email_address or "").strip().lower()
        tenant_domain = self._domain_of(tenant_mailbox)
        if tenant_domain:
            domains.add(tenant_domain)

        return domains

    def _is_external_recipient(self, to_address: str) -> bool:
        recipient_domain = self._domain_of((to_address or "").strip().lower())
        if not recipient_domain:
            return False
        return recipient_domain not in self._internal_domains()

    async def _send_via_graph(
        self,
        token: str,
        mailbox: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> dict:
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
                logger.info("Email accepted by Graph transport: to=%s subject=%s", to_address, subject)
                return {"success": True, "to_address": to_address, "subject": subject}
            logger.error("Graph sendMail failed: %s %s", resp.status_code, resp.text)
            return {"success": False, "error": resp.text}

    def _send_via_smtp_fallback(self, to_address: str, subject: str, body: str) -> dict:
        host = os.environ.get("SMTP_FALLBACK_HOST", "").strip()
        port = int(os.environ.get("SMTP_FALLBACK_PORT", "587").strip() or "587")
        username = os.environ.get("SMTP_FALLBACK_USERNAME", "").strip()
        password = os.environ.get("SMTP_FALLBACK_PASSWORD", "").strip()
        from_address = os.environ.get("SMTP_FALLBACK_FROM_ADDRESS", "").strip() or self._ctx.config.email_address or ""
        starttls_enabled = os.environ.get("SMTP_FALLBACK_STARTTLS", "true").strip().lower() == "true"

        if not host or not from_address:
            return {"success": False, "error": "SMTP fallback is not configured"}

        try:
            msg = EmailMessage()
            msg["From"] = from_address
            msg["To"] = to_address
            msg["Subject"] = subject if subject.startswith("RE:") else f"RE: {subject}"
            msg.set_content(body)

            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if starttls_enabled:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)

            logger.info("Email sent via SMTP fallback: to=%s subject=%s", to_address, subject)
            return {"success": True, "to_address": to_address, "subject": subject, "provider": "smtp"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("SMTP fallback failed: to=%s", to_address)
            return {"success": False, "error": str(exc)}

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
        recipient = (to_address or "").strip()
        is_external = self._is_external_recipient(recipient)
        external_route_mode = os.environ.get("EMAIL_EXTERNAL_ROUTE_MODE", DEFAULT_EXTERNAL_ROUTE_MODE).strip().lower()
        fallback_provider = (
            os.environ.get("EMAIL_EXTERNAL_FALLBACK_PROVIDER", DEFAULT_EXTERNAL_FALLBACK_PROVIDER).strip().lower()
        )
        delegated_enabled = bool(
            os.environ.get("GRAPH_DELEGATED_REFRESH_TOKEN", "").strip()
            or os.environ.get("GRAPH_DELEGATED_ACCESS_TOKEN", "").strip()
        )

        if not cfg.graph_mailbox_user_id or not cfg.graph_client_id:
            if is_external and fallback_provider == "smtp":
                smtp_result = self._send_via_smtp_fallback(recipient, subject, body)
                if smtp_result.get("success"):
                    return smtp_result
            logger.warning("Graph API未設定: モック送信 to=%s subject=%s", recipient, subject)
            return {"success": True, "mock": True, "to_address": recipient, "subject": subject}

        try:
            mailbox = cfg.graph_mailbox_user_id

            if is_external and external_route_mode in {"delegated_only", "delegated_first"} and delegated_enabled:
                try:
                    token = await self._get_graph_delegated_token()
                    delegated_mailbox = os.environ.get("GRAPH_DELEGATED_SEND_AS_USER_ID", "").strip() or mailbox
                    delegated_result = await self._send_via_graph(token, delegated_mailbox, recipient, subject, body)
                    if delegated_result.get("success"):
                        delegated_result["provider"] = "graph_delegated"
                        return delegated_result
                except Exception:  # noqa: BLE001
                    logger.exception("Delegated Graph send failed: to=%s", recipient)
                    if external_route_mode == "delegated_only":
                        return {"success": False, "error": "Delegated Graph send failed"}

            if is_external and fallback_provider == "smtp" and external_route_mode in {"delegated_first", "smtp_only"}:
                smtp_result = self._send_via_smtp_fallback(recipient, subject, body)
                if smtp_result.get("success") or external_route_mode == "smtp_only":
                    return smtp_result

            token = await self._get_graph_token()
            app_only_result = await self._send_via_graph(token, mailbox, recipient, subject, body)
            if app_only_result.get("success"):
                app_only_result["provider"] = "graph_app_only"
            return app_only_result
        except Exception:
            logger.exception("Email send error: to=%s", recipient)
            return {"success": False, "error": "送信中にエラーが発生しました"}

    # ── 受注確認メール ─────────────────────────────────────────────────────

    @kernel_function(
        name="send_order_confirmation_email",
        description="受注確定後に顧客のメールアドレスへ受注確認メールを送信する",
    )
    async def send_order_confirmation_email(
        self,
        customer_id: Annotated[str, "顧客ID"],
        customer_name: Annotated[str, "顧客名"],
        order_id: Annotated[str, "受注ID"],
        items_summary: Annotated[str, "注文商品の一覧テキスト（例: りんご10箱、バナナ5kg）"],
        delivery_date: Annotated[str, "配送予定日（YYYY-MM-DD形式）"] = "",
        delivery_time_slot: Annotated[str, "配送時間帯"] = "",
    ) -> dict:
        """顧客のメールアドレスを取得し、受注確認メールを送信する."""
        customer_repo = self._ctx.get_connector("ICustomerRepository")
        customer = await customer_repo.get_by_id(self._ctx.tenant_id, customer_id)
        if not customer:
            logger.warning("Customer %s not found, skipping email", customer_id)
            return {"success": False, "error": f"Customer {customer_id} not found"}

        if not customer.email:
            logger.info("Customer %s has no email address, skipping", customer_id)
            return {"success": False, "error": "Customer has no email address"}

        subject = f"【受注確認】ご注文 {order_id} を承りました"
        body_html = _build_order_confirmation_html(
            customer_name=customer_name,
            order_id=order_id,
            items_summary=items_summary,
            delivery_date=delivery_date,
            delivery_time_slot=delivery_time_slot,
        )

        try:
            email_service = self._ctx.get_connector("IEmailService")
        except ValueError:
            logger.warning("IEmailService not configured for tenant %s", self._ctx.tenant_id)
            return {"success": False, "error": "Email service not configured"}

        result = await email_service.send_email(
            tenant_id=self._ctx.tenant_id,
            to_address=customer.email,
            subject=subject,
            body_html=body_html,
        )
        if result.get("success"):
            logger.info("Order confirmation email sent to %s for order %s", customer.email, order_id)
        else:
            logger.error("Failed to send order confirmation email: %s", result.get("error"))
        return result


def _build_order_confirmation_html(
    *,
    customer_name: str,
    order_id: str,
    items_summary: str,
    delivery_date: str,
    delivery_time_slot: str,
) -> str:
    """受注確認メールのHTML本文を生成する."""
    from datetime import date as _date

    delivery_info = ""
    if delivery_date:
        delivery_info += f"<p><strong>配送予定日:</strong> {delivery_date}</p>"
    if delivery_time_slot:
        delivery_info += f"<p><strong>配送時間帯:</strong> {delivery_time_slot}</p>"

    items_html = ""
    for line in items_summary.replace("、", "\n").splitlines():
        line = line.strip()
        if line:
            items_html += f"<li>{line}</li>"
    if not items_html:
        items_html = f"<li>{items_summary}</li>"

    return f"""\
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family: 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif; color: #333; line-height: 1.6;">
  <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #2c5f2d; border-bottom: 2px solid #2c5f2d; padding-bottom: 8px;">
      受注確認
    </h2>
    <p>{customer_name} 様</p>
    <p>いつもお世話になっております。<br>
    以下のご注文を承りました。</p>

    <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
      <tr style="background: #f5f5f5;">
        <td style="padding: 8px 12px; font-weight: bold;">受注番号</td>
        <td style="padding: 8px 12px;">{order_id}</td>
      </tr>
      <tr>
        <td style="padding: 8px 12px; font-weight: bold;">受注日</td>
        <td style="padding: 8px 12px;">{_date.today().isoformat()}</td>
      </tr>
    </table>

    <h3 style="color: #555;">ご注文内容</h3>
    <ul style="padding-left: 20px;">{items_html}</ul>

    {delivery_info}

    <hr style="border: none; border-top: 1px solid #ddd; margin: 24px 0;">
    <p style="font-size: 12px; color: #999;">
      本メールはシステムから自動送信されています。<br>
      ご不明な点がございましたら担当者までお問い合わせください。
    </p>
  </div>
</body>
</html>"""
