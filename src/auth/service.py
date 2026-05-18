from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.auth.models import CurrentUser, UserInDB

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "24"))


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user: UserInDB) -> str:
    expire = datetime.now(UTC) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user.user_id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "display_name": user.display_name,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> CurrentUser | None:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return CurrentUser(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            email=payload["email"],
            display_name=payload.get("display_name", ""),
            auth_provider="",
        )
    except JWTError:
        logger.debug("JWT decode failed", exc_info=True)
        return None


class UserStore:
    """User CRUD backed by Azure SQL via aioodbc."""

    def __init__(self, sql_connection_string: str):
        from src.connectors.adapters._sql_util import to_odbc_dsn

        self._conn_str = to_odbc_dsn(sql_connection_string)

    async def _get_connection(self):
        import aioodbc

        return await aioodbc.connect(dsn=self._conn_str)

    async def find_by_email(self, email: str) -> tuple[UserInDB, str | None] | None:
        conn = await self._get_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, tenant_id, email, password_hash, display_name, "
                    "auth_provider, entra_oid, active FROM users WHERE email = ?",
                    (email,),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                user = UserInDB(
                    user_id=row[0],
                    tenant_id=row[1],
                    email=row[2],
                    display_name=row[4],
                    auth_provider=row[5],
                    entra_oid=row[6],
                    active=bool(row[7]),
                )
                return user, row[3]  # user, password_hash
        finally:
            await conn.close()

    async def find_by_entra_oid(self, oid: str) -> UserInDB | None:
        conn = await self._get_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, tenant_id, email, display_name, "
                    "auth_provider, entra_oid, active FROM users WHERE entra_oid = ?",
                    (oid,),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                return UserInDB(
                    user_id=row[0],
                    tenant_id=row[1],
                    email=row[2],
                    display_name=row[3],
                    auth_provider=row[4],
                    entra_oid=row[5],
                    active=bool(row[6]),
                )
        finally:
            await conn.close()

    async def create_user(
        self,
        tenant_id: str,
        email: str,
        display_name: str,
        password_hash: str | None = None,
        auth_provider: str = "local",
        entra_oid: str | None = None,
    ) -> UserInDB:
        user_id = f"U-{uuid.uuid4().hex[:8].upper()}"
        conn = await self._get_connection()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO users (user_id, tenant_id, email, password_hash, "
                    "display_name, auth_provider, entra_oid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        tenant_id,
                        email,
                        password_hash,
                        display_name,
                        auth_provider,
                        entra_oid,
                    ),
                )
                await conn.commit()
            return UserInDB(
                user_id=user_id,
                tenant_id=tenant_id,
                email=email,
                display_name=display_name,
                auth_provider=auth_provider,
                entra_oid=entra_oid,
            )
        finally:
            await conn.close()
