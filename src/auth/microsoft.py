from __future__ import annotations

import logging
import os

import httpx
from jose import jwt
from jose.exceptions import JWTError

logger = logging.getLogger(__name__)

ENTRA_CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID", "")

# Single-tenant enforcement: ENTRA_TENANT_ID is the primary setting.
# AZURE_AD_ALLOWED_TENANTS (comma-separated) overrides when set (multi-tenant mode).
ENTRA_TENANT_ID = os.environ.get("ENTRA_TENANT_ID", "")
_RAW_ALLOWED_TIDS = os.environ.get("AZURE_AD_ALLOWED_TENANTS", "")
ALLOWED_TIDS: set[str] = (
    {t.strip() for t in _RAW_ALLOWED_TIDS.split(",") if t.strip()}
    if _RAW_ALLOWED_TIDS
    else ({ENTRA_TENANT_ID} if ENTRA_TENANT_ID else set())
)

# Optional email-domain allowlist (lowercase).
_RAW_ALLOWED_DOMAINS = os.environ.get("AZURE_AD_ALLOWED_DOMAINS", "")
ALLOWED_DOMAINS = {d.strip().lower() for d in _RAW_ALLOWED_DOMAINS.split(",") if d.strip()}

# JWKS from the "organizations" endpoint covers all Entra tenants;
# issuer/tid is validated manually against ALLOWED_TIDS.
JWKS_URL = "https://login.microsoftonline.com/organizations/discovery/v2.0/keys"
ISSUER_TEMPLATE = "https://login.microsoftonline.com/{tid}/v2.0"

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
    or None if validation fails (signature, expiry, audience, issuer, tid, domain).
    """
    if not ENTRA_CLIENT_ID:
        logger.error("ENTRA_CLIENT_ID is not set — cannot validate Microsoft tokens")
        return None
    if not ALLOWED_TIDS:
        logger.error("ENTRA_TENANT_ID / AZURE_AD_ALLOWED_TENANTS not set — refusing all SSO logins (fail-closed)")
        return None

    try:
        jwks = await _fetch_jwks()

        unverified_header = jwt.get_unverified_header(id_token)
        kid = unverified_header.get("kid")
        rsa_key = next((k for k in jwks.get("keys", []) if k["kid"] == kid), None)

        if not rsa_key:
            logger.warning("No matching JWKS key found for kid=%s", kid)
            return None

        payload = jwt.decode(
            id_token,
            rsa_key,
            algorithms=["RS256"],
            audience=ENTRA_CLIENT_ID,
            options={"verify_iss": False},  # issuer checked manually below
        )

        tid = payload.get("tid", "")
        if tid not in ALLOWED_TIDS:
            logger.warning("Rejected Microsoft token: tid=%s not in allowlist", tid)
            return None

        expected_iss = ISSUER_TEMPLATE.format(tid=tid)
        actual_iss = payload.get("iss", "")
        if actual_iss != expected_iss:
            logger.warning("Issuer mismatch: expected %s, got %s", expected_iss, actual_iss)
            return None

        email = payload.get("preferred_username", payload.get("email", ""))
        if ALLOWED_DOMAINS:
            if "@" not in email:
                logger.warning("Rejected Microsoft token: no email/UPN claim")
                return None
            domain = email.rsplit("@", 1)[1].lower()
            if domain not in ALLOWED_DOMAINS:
                logger.warning("Rejected Microsoft token: domain %s not in allowlist", domain)
                return None

        return {
            "oid": payload.get("oid", ""),
            "email": email,
            "name": payload.get("name", ""),
            "tid": tid,
        }
    except JWTError:
        logger.exception("Microsoft ID token validation failed")
        return None
    except httpx.HTTPError:
        logger.exception("Failed to fetch Microsoft JWKS")
        return None
