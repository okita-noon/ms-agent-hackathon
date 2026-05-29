from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from src.auth.dependencies import get_current_user
from src.auth.microsoft import validate_microsoft_id_token
from src.auth.models import (
    CurrentUser,
    LoginRequest,
    MicrosoftLoginRequest,
    RegisterRequest,
    TokenResponse,
)
from src.auth.service import (
    UserStore,
    create_access_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(tags=["auth"])
AUTH_COOKIE_NAME = "foogent_access_token"


def _cookie_secure() -> bool:
    return os.environ.get("AUTH_COOKIE_SECURE", "true").lower() != "false"


def _cookie_samesite() -> str:
    value = os.environ.get("AUTH_COOKIE_SAMESITE", "none").lower()
    return value if value in {"lax", "strict", "none"} else "none"


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=int(os.environ.get("JWT_EXPIRE_HOURS", "24")) * 3600,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )


def _registration_enabled() -> bool:
    return os.environ.get("REGISTRATION_ENABLED", "false").lower() == "true"


def _registration_invite_token() -> str:
    return os.environ.get("REGISTRATION_INVITE_TOKEN", "")


def _get_user_store() -> UserStore:
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
    return UserStore(conn_str)


@auth_router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, response: Response):
    store = _get_user_store()
    result = await store.find_by_email(req.email)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
        )

    user, password_hash = result

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="アカウントが無効です",
        )

    if user.auth_provider != "local" or password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このアカウントはMicrosoftログインを使用してください",
        )

    if not verify_password(req.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="メールアドレスまたはパスワードが正しくありません",
        )

    token = create_access_token(user)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


@auth_router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest,
    response: Response,
    x_invite_token: str | None = Header(None, alias="X-Invite-Token"),
):
    if not _registration_enabled():
        # Endpoint must look like it does not exist when public registration is off.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    expected_token = _registration_invite_token()
    if not expected_token or not x_invite_token or x_invite_token != expected_token:
        logger.warning("Registration attempt with invalid or missing invite token: %s", req.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="招待トークンが必要です",
        )

    store = _get_user_store()
    existing = await store.find_by_email(req.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このメールアドレスは既に登録されています",
        )

    hashed = hash_password(req.password)
    user = await store.create_user(
        tenant_id=req.tenant_id,
        email=req.email,
        display_name=req.display_name,
        password_hash=hashed,
        auth_provider="local",
    )

    token = create_access_token(user)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


@auth_router.post("/microsoft", response_model=TokenResponse)
async def microsoft_login(req: MicrosoftLoginRequest, response: Response):
    claims = await validate_microsoft_id_token(req.id_token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Microsoftトークンの検証に失敗しました",
        )

    oid = claims["oid"]
    email = claims["email"]

    if not oid or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="トークンに必要な情報が含まれていません",
        )

    store = _get_user_store()

    # Auto-registration is disabled. Only pre-provisioned users may sign in via SSO.
    user = await store.find_by_entra_oid(oid)
    if user is None:
        result = await store.find_by_email(email)
        if not result:
            logger.warning(
                "SSO login rejected for unregistered user: email=%s oid=%s tid=%s",
                email,
                oid,
                claims.get("tid", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="アカウントが登録されていません。管理者にお問い合わせください。",
            )
        user, _ = result

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="アカウントが無効です",
        )

    token = create_access_token(user)
    _set_auth_cookie(response, token)
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


@auth_router.get("/me", response_model=CurrentUser)
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return user


@auth_router.post("/logout")
async def logout(response: Response):
    _clear_auth_cookie(response)
    return {"status": "ok"}
