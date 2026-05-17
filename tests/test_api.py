from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "foogent-api"


class TestRootRedirect:
    def test_redirects_to_dashboard(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert "/dashboard" in resp.headers["location"]


class TestLineWebhook:
    def test_returns_200_for_valid_request(self, client):
        with (
            patch("src.api.main.resolve_tenant_for_line") as mock_resolve,
            patch("src.api.main.LineWebhookHandler") as mock_handler_cls,
        ):
            from unittest.mock import MagicMock

            mock_ctx = MagicMock()
            mock_ctx.config.line_channel_secret = None
            mock_resolve.return_value = mock_ctx

            mock_handler = MagicMock()
            mock_handler.verify_signature.return_value = True
            mock_handler_cls.return_value = mock_handler

            resp = client.post(
                "/api/line-webhook",
                json={"events": []},
                headers={"x-line-signature": "test"},
            )
            assert resp.status_code == 200

    def test_rejects_invalid_signature(self, client):
        with (
            patch("src.api.main.resolve_tenant_for_line") as mock_resolve,
            patch("src.api.main.LineWebhookHandler") as mock_handler_cls,
        ):
            mock_ctx = MagicMock()
            mock_resolve.return_value = mock_ctx

            mock_handler = MagicMock()
            mock_handler.verify_signature.return_value = False
            mock_handler_cls.return_value = mock_handler

            resp = client.post(
                "/api/line-webhook",
                json={"events": []},
                headers={"x-line-signature": "bad-sig"},
            )
            assert resp.status_code == 403
