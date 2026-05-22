from __future__ import annotations

import json
import logging
import os

import msal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

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
    InMemoryUserStore,
    UserStore,
    create_access_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(tags=["auth"])

SSO_DEFAULT_TENANT = os.environ.get("SSO_DEFAULT_TENANT", "T-001")
ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "")
ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "")
ENTRA_CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET", "")
ENTRA_REDIRECT_URI = os.environ.get(
    "ENTRA_REDIRECT_URI", "http://localhost:8080/api/auth/callback/microsoft"
)

# MSAL flow state for the redirect flow (single-replica assumption)
_pending_flows: dict[str, dict] = {}


def _registration_enabled() -> bool:
    return os.environ.get("REGISTRATION_ENABLED", "false").lower() == "true"


def _registration_invite_token() -> str:
    return os.environ.get("REGISTRATION_INVITE_TOKEN", "")


_in_memory_store: InMemoryUserStore | None = None


def _get_user_store() -> UserStore | InMemoryUserStore:
    conn_str = os.environ.get("SQL_CONNECTION_STRING", "")
    if not conn_str:
        global _in_memory_store  # noqa: PLW0603
        if _in_memory_store is None:
            _in_memory_store = InMemoryUserStore()
            logger.warning("SQL_CONNECTION_STRING が未設定のため、インメモリ UserStore を使用します（ローカル開発用）")
        return _in_memory_store
    return UserStore(conn_str)


def _get_msal_app() -> msal.ConfidentialClientApplication:
    authority = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}"
    return msal.ConfidentialClientApplication(
        ENTRA_CLIENT_ID,
        authority=authority,
        client_credential=ENTRA_CLIENT_SECRET,
    )


def _js(value: str) -> str:
    """JSON-encode a string for safe embedding in a JS string literal."""
    return json.dumps(value, ensure_ascii=False)


# ── ID/PW ログイン ─────────────────────────────────────────────────────────────

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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アカウントが無効です")

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
async def register(
    req: RegisterRequest,
    x_invite_token: str | None = Header(None, alias="X-Invite-Token"),
):
    if not _registration_enabled():
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="このメールアドレスは既に登録されています")

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


# ── Microsoft SSO（トークン直接検証 — SPA向け後方互換） ────────────────────────

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
    name = claims.get("name") or email

    if not oid or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="トークンに必要な情報が含まれていません")

    store = _get_user_store()
    user = await store.find_by_entra_oid(oid)
    if user is None:
        result = await store.find_by_email(email)
        if result:
            user, _ = result
        else:
            user = await store.create_user(
                tenant_id=SSO_DEFAULT_TENANT,
                email=email,
                display_name=name,
                auth_provider="microsoft",
                entra_oid=oid,
            )
            logger.info("Auto-created SSO user: %s (%s)", email, user.user_id)

    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アカウントが無効です")

    token = create_access_token(user)
    return TokenResponse(
        access_token=token,
        tenant_id=user.tenant_id,
        display_name=user.display_name,
        email=user.email,
    )


# ── Microsoft SSO リダイレクトフロー ──────────────────────────────────────────

@auth_router.get("/login/microsoft")
async def login_microsoft():
    """Microsoft の認証ページへリダイレクトする。"""
    if not ENTRA_TENANT_ID or not ENTRA_CLIENT_ID or not ENTRA_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Microsoft SSO の設定が不足しています。管理者に連絡してください。",
        )

    app = _get_msal_app()
    flow = app.initiate_auth_code_flow(
        scopes=["User.Read"],
        redirect_uri=ENTRA_REDIRECT_URI,
    )
    _pending_flows[flow["state"]] = flow

    response = RedirectResponse(url=flow["auth_uri"])
    response.set_cookie("oauth_state", flow["state"], httponly=True, samesite="lax", max_age=300)
    return response


@auth_router.get("/callback/microsoft")
async def callback_microsoft(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Microsoft からのコールバックを受け取り、JWT を発行してダッシュボードへリダイレクトする。"""
    if error:
        logger.warning("Microsoft OAuth error: %s - %s", error, error_description)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Microsoft認証エラー: {error_description or error}",
        )

    stored_state = request.cookies.get("oauth_state")
    if not state or stored_state != state or state not in _pending_flows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="セッションが無効です。再度ログインしてください。",
        )

    flow = _pending_flows.pop(state)
    app = _get_msal_app()
    result = app.acquire_token_by_auth_code_flow(flow, dict(request.query_params))

    if "error" in result:
        logger.error("MSAL token acquisition failed: %s", result)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"トークン取得に失敗しました: {result.get('error_description', result['error'])}",
        )

    claims = result.get("id_token_claims", {})

    # シングルテナント強制
    tid = claims.get("tid", "")
    if tid != ENTRA_TENANT_ID:
        logger.warning("Login attempt from unauthorized tenant: %s", tid)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="このアカウントはログインが許可されていません。",
        )

    oid = claims.get("oid", "")
    email = claims.get("preferred_username") or claims.get("email", "")
    name = claims.get("name") or email

    if not oid or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="アカウント情報を取得できませんでした。")

    store = _get_user_store()
    user = await store.find_by_entra_oid(oid)
    if user is None:
        result_by_email = await store.find_by_email(email)
        if result_by_email:
            user, _ = result_by_email
        else:
            user = await store.create_user(
                tenant_id=SSO_DEFAULT_TENANT,
                email=email,
                display_name=name,
                auth_provider="microsoft",
                entra_oid=oid,
            )
            logger.info("Auto-created SSO user via redirect flow: %s (%s)", email, user.user_id)

    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="アカウントが無効です。管理者に連絡してください。")

    token = create_access_token(user)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>ログイン中...</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center">
  <div class="text-center">
    <div class="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
    <p class="text-gray-500 text-sm">ダッシュボードへ移動中...</p>
  </div>
  <script>
    localStorage.setItem('auth_token', {_js(token)});
    localStorage.setItem('auth_user_name', {_js(name)});
    localStorage.setItem('auth_user_email', {_js(email)});
    window.location.replace('/dashboard/');
  </script>
</body>
</html>"""

    response = HTMLResponse(html)
    response.delete_cookie("oauth_state")
    return response


# ── 現在のユーザー情報 ─────────────────────────────────────────────────────────

@auth_router.get("/me", response_model=CurrentUser)
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return user
