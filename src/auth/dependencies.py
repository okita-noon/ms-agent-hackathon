from __future__ import annotations

import os

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.models import CurrentUser
from src.auth.service import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
AUTH_COOKIE_NAME = "foogent_access_token"


def _allowed_origins() -> set[str]:
    return {origin.strip() for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",") if origin.strip()}


def _is_safe_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True

    allowed = _allowed_origins()
    if origin in allowed:
        return True

    # Local development without FRONTEND_ORIGINS should still work.
    return origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    cookie_token: str | None = Cookie(None, alias=AUTH_COOKIE_NAME),
) -> CurrentUser:
    token = credentials.credentials if credentials else cookie_token
    using_cookie = credentials is None and cookie_token is not None

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
        )

    if using_cookie and request.method not in ("GET", "HEAD", "OPTIONS") and not _is_safe_origin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="許可されていないOriginからのリクエストです",
        )

    user = decode_access_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンが無効です",
        )
    return user


async def get_tenant_id(user: CurrentUser = Depends(get_current_user)) -> str:
    return user.tenant_id
