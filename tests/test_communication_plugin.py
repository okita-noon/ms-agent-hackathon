from __future__ import annotations

from email.header import decode_header, make_header
from email.utils import parseaddr
from types import SimpleNamespace
from unittest.mock import patch

from src.plugins.communication_plugin import CommunicationPlugin


def test_smtp_reply_uses_configured_sender_name(monkeypatch):
    monkeypatch.setenv("SMTP_FALLBACK_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FALLBACK_FROM_ADDRESS", "orders@example.com")
    monkeypatch.setenv("SMTP_FALLBACK_FROM_NAME", "受注窓口")
    monkeypatch.setenv("SMTP_FALLBACK_STARTTLS", "false")

    tenant_ctx = SimpleNamespace(config=SimpleNamespace(email_address="orders@example.com"))
    plugin = CommunicationPlugin(tenant_ctx)
    with patch("src.plugins.communication_plugin.smtplib.SMTP") as smtp_cls:
        result = plugin._send_via_smtp_fallback("customer@example.com", "注文", "承りました")

    assert result["success"] is True
    message = smtp_cls.return_value.__enter__.return_value.send_message.call_args.args[0]
    encoded_name, address = parseaddr(message["From"])
    assert str(make_header(decode_header(encoded_name))) == "受注窓口"
    assert address == "orders@example.com"
