"""Bearer JWT authentication dependency for the headless API (020).

Validates Azure AD JWT tokens issued to HARNESS_AZURE_CLIENT_ID against the
tenant's JWKS endpoint. When HARNESS_AUTH_ENABLED is false (local dev), returns
a synthetic user without token validation.
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _get_jwks_client():
    """Module-level PyJWKClient singleton (cached after first call)."""
    import jwt

    tenant_id = os.environ.get("HARNESS_AZURE_TENANT_ID", "")
    jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return jwt.PyJWKClient(jwks_uri, cache_keys=True)


def require_api_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency — returns a user identity dict or raises 401.

    Identity dict keys: ``oid`` (Azure object ID), ``name`` (display name).
    When HARNESS_AUTH_ENABLED is falsy, returns a synthetic local-dev user
    without contacting Azure AD.
    """
    from harness.auth.config import is_auth_enabled

    if not is_auth_enabled():
        return {"oid": "local-dev", "name": "Local Dev"}

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        import jwt

        client_id = os.environ.get("HARNESS_AZURE_CLIENT_ID", "")
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "oid": payload.get("oid") or payload.get("sub", ""),
        "name": payload.get("preferred_username") or payload.get("name", ""),
    }
