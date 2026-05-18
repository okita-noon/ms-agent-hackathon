from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.dependencies import get_current_user, get_tenant_id
from src.auth.endpoints import auth_router
from src.auth.models import CurrentUser, UserInDB
from src.auth.service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ── Password hashing ─────────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("demo1234")
        assert verify_password("demo1234", hashed)
        assert not verify_password("wrong", hashed)

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


# ── JWT ───────────────────────────────────────────────────────────────────────


class TestJWT:
    def _make_user(self) -> UserInDB:
        return UserInDB(
            user_id="U-001",
            tenant_id="T-001",
            email="test@example.com",
            display_name="Test User",
            auth_provider="local",
        )

    def test_create_and_decode(self):
        user = self._make_user()
        token = create_access_token(user)
        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded.user_id == "U-001"
        assert decoded.tenant_id == "T-001"
        assert decoded.email == "test@example.com"

    def test_invalid_token_returns_none(self):
        assert decode_access_token("invalid.token.here") is None
        assert decode_access_token("") is None


# ── Dependencies ──────────────────────────────────────────────────────────────


class TestDependencies:
    @pytest.mark.asyncio
    async def test_get_current_user_with_valid_token(self):
        user = UserInDB(
            user_id="U-001",
            tenant_id="T-001",
            email="test@example.com",
            display_name="Test",
            auth_provider="local",
        )
        token = create_access_token(user)

        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = await get_current_user(creds)
        assert result.user_id == "U-001"
        assert result.tenant_id == "T-001"

    @pytest.mark.asyncio
    async def test_get_current_user_no_creds_raises_401(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_bad_token_raises_401(self):
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_tenant_id(self):
        user = CurrentUser(
            user_id="U-001",
            tenant_id="T-002",
            email="test@example.com",
            display_name="Test",
            auth_provider="local",
        )
        tid = await get_tenant_id(user)
        assert tid == "T-002"


# ── Auth endpoints (via TestClient) ───────────────────────────────────────────


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/auth")
    return app


def _mock_user(
    user_id: str = "U-001",
    tenant_id: str = "T-001",
    email: str = "admin@maruyama.example.com",
    display_name: str = "丸山 太郎",
    auth_provider: str = "local",
) -> UserInDB:
    return UserInDB(
        user_id=user_id,
        tenant_id=tenant_id,
        email=email,
        display_name=display_name,
        auth_provider=auth_provider,
    )


class TestLoginEndpoint:
    def test_login_success(self):
        app = _make_app()
        user = _mock_user()
        pw_hash = hash_password("demo1234")
        mock_store = AsyncMock()
        mock_store.find_by_email.return_value = (user, pw_hash)

        with patch("src.auth.endpoints._get_user_store", return_value=mock_store):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/login",
                json={"email": "admin@maruyama.example.com", "password": "demo1234"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["tenant_id"] == "T-001"
        assert data["display_name"] == "丸山 太郎"

    def test_login_wrong_password(self):
        app = _make_app()
        user = _mock_user()
        pw_hash = hash_password("demo1234")
        mock_store = AsyncMock()
        mock_store.find_by_email.return_value = (user, pw_hash)

        with patch("src.auth.endpoints._get_user_store", return_value=mock_store):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/login",
                json={"email": "admin@maruyama.example.com", "password": "wrong"},
            )

        assert resp.status_code == 401

    def test_login_user_not_found(self):
        app = _make_app()
        mock_store = AsyncMock()
        mock_store.find_by_email.return_value = None

        with patch("src.auth.endpoints._get_user_store", return_value=mock_store):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/login",
                json={"email": "unknown@example.com", "password": "demo1234"},
            )

        assert resp.status_code == 401

    def test_login_sso_user_rejects_password(self):
        app = _make_app()
        user = _mock_user(auth_provider="microsoft")
        mock_store = AsyncMock()
        mock_store.find_by_email.return_value = (user, None)

        with patch("src.auth.endpoints._get_user_store", return_value=mock_store):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/login",
                json={"email": "admin@maruyama.example.com", "password": "demo1234"},
            )

        assert resp.status_code == 400
        assert "Microsoft" in resp.json()["detail"]


class TestRegisterEndpoint:
    _INVITE = "test-invite-token-abc123"
    _REGISTER_ENV = {
        "REGISTRATION_ENABLED": "true",
        "REGISTRATION_INVITE_TOKEN": _INVITE,
    }

    def test_register_success(self):
        app = _make_app()
        mock_store = AsyncMock()
        mock_store.find_by_email.return_value = None
        mock_store.create_user.return_value = _mock_user()

        with (
            patch.dict("os.environ", self._REGISTER_ENV),
            patch("src.auth.endpoints._get_user_store", return_value=mock_store),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "newpass",
                    "display_name": "New User",
                    "tenant_id": "T-001",
                },
                headers={"X-Invite-Token": self._INVITE},
            )

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_register_duplicate_email(self):
        app = _make_app()
        mock_store = AsyncMock()
        mock_store.find_by_email.return_value = (_mock_user(), "hash")

        with (
            patch.dict("os.environ", self._REGISTER_ENV),
            patch("src.auth.endpoints._get_user_store", return_value=mock_store),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/register",
                json={
                    "email": "admin@maruyama.example.com",
                    "password": "pass",
                    "display_name": "Dup",
                    "tenant_id": "T-001",
                },
                headers={"X-Invite-Token": self._INVITE},
            )

        assert resp.status_code == 409

    def test_register_disabled_returns_404(self):
        """When REGISTRATION_ENABLED is false (default), endpoint must look absent."""
        app = _make_app()
        with patch.dict("os.environ", {"REGISTRATION_ENABLED": "false"}):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "p",
                    "display_name": "x",
                    "tenant_id": "T-001",
                },
                headers={"X-Invite-Token": self._INVITE},
            )
        assert resp.status_code == 404

    def test_register_missing_invite_token_forbidden(self):
        app = _make_app()
        with patch.dict("os.environ", self._REGISTER_ENV):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "p",
                    "display_name": "x",
                    "tenant_id": "T-001",
                },
            )
        assert resp.status_code == 403

    def test_register_wrong_invite_token_forbidden(self):
        app = _make_app()
        with patch.dict("os.environ", self._REGISTER_ENV):
            client = TestClient(app)
            resp = client.post(
                "/api/auth/register",
                json={
                    "email": "new@example.com",
                    "password": "p",
                    "display_name": "x",
                    "tenant_id": "T-001",
                },
                headers={"X-Invite-Token": "wrong-token"},
            )
        assert resp.status_code == 403


class TestMeEndpoint:
    def test_me_with_valid_token(self):
        app = _make_app()
        user = _mock_user()
        token = create_access_token(user)

        client = TestClient(app)
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "U-001"
        assert data["tenant_id"] == "T-001"

    def test_me_without_token(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401


class TestProtectedEndpoints:
    """Verify business endpoints now require auth."""

    def test_orders_requires_auth(self):
        from src.api.main import app

        client = TestClient(app)
        resp = client.get("/api/orders")
        assert resp.status_code in (401, 403)

    def test_health_is_public(self):
        from src.api.main import app

        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
