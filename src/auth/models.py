from __future__ import annotations

from pydantic import BaseModel


class UserInDB(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    auth_provider: str = "local"  # 'local' | 'microsoft'
    entra_oid: str | None = None
    active: bool = True


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    tenant_id: str


class MicrosoftLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    display_name: str
    email: str


class CurrentUser(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    auth_provider: str
