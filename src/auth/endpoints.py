from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status

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

# Default tenant for SSO auto-registration
SSO_DEFAULT_TENANT = os.environ.get("SSO_DEFAULT_TENANT", "T-001")


def _get_user_store() -> UserStore:
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
    return UserStore(conn_str)


@auth_router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
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
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


@auth_router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
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
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


@auth_router.post("/microsoft", response_model=TokenResponse)
async def microsoft_login(req: MicrosoftLoginRequest):
    claims = await validate_microsoft_id_token(req.id_token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Microsoftトークンの検証に失敗しました",
        )

    oid = claims["oid"]
    email = claims["email"]
    name = claims["name"] or email

    if not oid or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="トークンに必要な情報が含まれていません",
        )

    store = _get_user_store()

    # Check if user already exists by Entra OID
    user = await store.find_by_entra_oid(oid)
    if user is None:
        # Check by email (may have been pre-registered)
        result = await store.find_by_email(email)
        if result:
            user, _ = result
        else:
            # Auto-create new user
            user = await store.create_user(
                tenant_id=SSO_DEFAULT_TENANT,
                email=email,
                display_name=name,
                auth_provider="microsoft",
                entra_oid=oid,
            )
            logger.info("Auto-created SSO user: %s (%s)", email, user.user_id)

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="アカウントが無効です",
        )

    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


@auth_router.get("/me", response_model=CurrentUser)
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return user
