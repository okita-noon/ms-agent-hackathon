from __future__ import annotations

import logging
import os

import httpx
from jose import jwt
from jose.exceptions import JWTError

logger = logging.getLogger(__name__)

ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "")
ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "common")
JWKS_URL = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"
ISSUER_PREFIX = "https://login.microsoftonline.com/"

_jwks_cache: dict | None = None


async def _fetch_jwks() -> dict:
    global _jwks_cache  # noqa: PLW0603
    if _jwks_cache is not None:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(JWKS_URL)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache


async def validate_microsoft_id_token(id_token: str) -> dict | None:
    """Validate a Microsoft Entra ID token and return claims.

    Returns dict with keys: oid, email, name, tid (tenant)
    or None if validation fails.
    """
    if not ENTRA_CLIENT_ID:
        logger.error("ENTRA_CLIENT_ID is not set — cannot validate Microsoft tokens")
        return None

    try:
        jwks = await _fetch_jwks()

        # Decode header to find the right key
        unverified_header = jwt.get_unverified_header(id_token)
        kid = unverified_header.get("kid")

        # Find matching key
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key["kid"] == kid:
                rsa_key = key
                break

        if not rsa_key:
            logger.warning("No matching key found for kid=%s", kid)
            return None

        payload = jwt.decode(
            id_token,
            rsa_key,
            algorithms=["RS256"],
            audience=ENTRA_CLIENT_ID,
            options={"verify_iss": False},  # Multi-tenant: issuer varies
        )

        return {
            "oid": payload.get("oid", ""),
            "email": payload.get("preferred_username", payload.get("email", "")),
            "name": payload.get("name", ""),
            "tid": payload.get("tid", ""),
        }
    except JWTError:
        logger.exception("Microsoft ID token validation failed")
        return None
    except httpx.HTTPError:
        logger.exception("Failed to fetch Microsoft JWKS")
        return None
