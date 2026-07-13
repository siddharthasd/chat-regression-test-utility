"""Bearer JWT authentication dependency for the headless API (020).

Validates Azure AD M2M (client-credentials) tokens against the tenant's JWKS
endpoint. The expected audience is HARNESS_AZURE_API_AUDIENCE, defaulting to
HARNESS_AZURE_CLIENT_ID when not set — mirroring the org-standard pattern
where `resource` in the token request defaults to the target app's client ID.

When HARNESS_AUTH_ENABLED is false (local dev), returns a synthetic user
without token validation.
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def _api_audience() -> str:
    """Return the expected `aud` claim value for incoming Bearer tokens.

    Reads HARNESS_AZURE_API_AUDIENCE; falls back to HARNESS_AZURE_CLIENT_ID.
    Matches the org-standard M2M pattern: qual-brew sets `resource=<audience>`
    when acquiring its token, and that value lands in the token's `aud` claim.
    """
    return (
        os.environ.get("HARNESS_AZURE_API_AUDIENCE")
        or os.environ.get("HARNESS_AZURE_CLIENT_ID", "")
    )


@lru_cache(maxsize=1)
def _get_jwks_client():
    """PyJWKClient singleton — built from HARNESS_AZURE_TENANT_ID."""
    import jwt

    tenant_id = os.environ.get("HARNESS_AZURE_TENANT_ID", "")
    jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return jwt.PyJWKClient(jwks_uri, cache_keys=True)


def require_api_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency — returns a caller identity dict or raises 401.

    Identity dict keys:
      ``oid``  — Azure object ID of the calling service principal (M2M).
      ``name`` — app display name or UPN from the token.

    When HARNESS_AUTH_ENABLED is falsy, returns a synthetic local-dev identity
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

        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=_api_audience(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "oid": payload.get("oid") or payload.get("sub", ""),
        "name": payload.get("app_displayname") or payload.get("appid", ""),
    }
