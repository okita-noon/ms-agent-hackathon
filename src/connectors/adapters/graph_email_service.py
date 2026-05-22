from __future__ import annotations

import logging

import httpx

from src.models.tenant import ConnectorConfig

logger = logging.getLogger(__name__)


class GraphEmailService:
    """Microsoft Graph API を使用したメール送信アダプタ.

    ConnectorConfig の設定:
        type: "microsoft_graph"
        endpoint: "https://graph.microsoft.com/v1.0"  (省略時はデフォルト)
        extra:
            tenant_id: Entra ID テナントID
            client_id: アプリ登録のクライアントID
            client_secret: アプリ登録のクライアントシークレット
            sender_email: 送信元メールアドレス (例: orders@example.com)
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def __init__(self, config: ConnectorConfig):
        self._config = config
        self._base_url = config.endpoint or self.GRAPH_BASE_URL
        self._entra_tenant_id = config.extra.get("tenant_id", "")
        self._client_id = config.extra.get("client_id", "")
        self._client_secret = config.extra.get("client_secret", "")
        self._sender_email = config.extra.get("sender_email", "")
        self._access_token: str | None = None

    async def _get_access_token(self) -> str:
        """Client Credentials フローで Graph API のアクセストークンを取得."""
        if self._access_token:
            return self._access_token

        token_url = self.TOKEN_URL_TEMPLATE.format(tenant_id=self._entra_tenant_id)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            if resp.status_code != 200:
                logger.error("Failed to get Graph API token: %s %s", resp.status_code, resp.text)
                raise RuntimeError(f"Graph API token acquisition failed: {resp.status_code}")
            data = resp.json()
            self._access_token = data["access_token"]
            return self._access_token

    async def send_email(
        self,
        tenant_id: str,
        to_address: str,
        subject: str,
        body_html: str,
    ) -> dict:
        """Microsoft Graph API でメールを送信する.

        Graph API: POST /users/{sender}/sendMail
        必要な権限: Mail.Send (Application)
        """
        try:
            token = await self._get_access_token()
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}

        url = f"{self._base_url}/users/{self._sender_email}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body_html,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_address,
                        }
                    }
                ],
            },
            "saveToSentItems": False,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )

        if resp.status_code == 202:
            logger.info("Email sent successfully to %s (subject: %s)", to_address, subject)
            return {"success": True}

        if resp.status_code == 401:
            logger.warning("Graph API token expired, refreshing...")
            self._access_token = None
            try:
                token = await self._get_access_token()
            except RuntimeError as exc:
                return {"success": False, "error": str(exc)}

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )
            if resp.status_code == 202:
                logger.info("Email sent successfully (retry) to %s", to_address)
                return {"success": True}

        logger.error("Graph API sendMail failed: %s %s", resp.status_code, resp.text)
        return {"success": False, "error": f"Graph API error {resp.status_code}: {resp.text[:200]}"}
