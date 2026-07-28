"""Thin wrapper over MSAL for Azure AD Authorization Code + PKCE flow (015)."""

from __future__ import annotations

import msal
import structlog

log = structlog.get_logger(__name__)


def _app(cfg: dict) -> msal.ConfidentialClientApplication:
    log.debug("sso.msal_app_created", client_id=cfg["client_id"], tenant_id=cfg["tenant_id"])
    return msal.ConfidentialClientApplication(
        client_id=cfg["client_id"],
        client_credential=cfg["client_secret"],
        authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
    )


_SCOPES = ["openid", "profile", "email"]


def initiate_flow(cfg: dict) -> dict:
    """Begin the auth code + PKCE flow; returns a flow dict to store in session."""
    log.debug("sso.flow_initiating", client_id=cfg["client_id"], scopes=_SCOPES)
    result = _app(cfg).initiate_auth_code_flow(
        scopes=_SCOPES,
        redirect_uri=cfg.get("redirect_uri") or None,
    )
    log.debug("sso.flow_initiated", redirect_uri=cfg.get("redirect_uri"))
    return result


def complete_flow(cfg: dict, flow: dict, auth_response: dict) -> dict:
    """Exchange the auth-code response for tokens; returns the id_token_claims dict."""
    log.debug("sso.flow_completing", client_id=cfg["client_id"])
    result = _app(cfg).acquire_token_by_auth_code_flow(flow, auth_response)
    if "error" in result:
        log.debug(
            "sso.flow_failed",
            error=result.get("error"),
            description=(result.get("error_description") or "")[:200],
        )
        raise ValueError(result.get("error_description") or result["error"])
    claims = result["id_token_claims"]
    log.debug(
        "sso.flow_completed",
        oid=claims.get("oid") or claims.get("sub"),
        upn=claims.get("userprincipalname", ""),
    )
    return claims
