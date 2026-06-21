"""Thin wrapper over MSAL for Azure AD Authorization Code + PKCE flow (015)."""

from __future__ import annotations

import msal


def _app(cfg: dict) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=cfg["client_id"],
        client_credential=cfg["client_secret"],
        authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
    )


_SCOPES = ["openid", "profile", "email"]


def initiate_flow(cfg: dict) -> dict:
    """Begin the auth code + PKCE flow; returns a flow dict to store in session."""
    return _app(cfg).initiate_auth_code_flow(
        scopes=_SCOPES,
        redirect_uri=cfg.get("redirect_uri") or None,
    )


def complete_flow(cfg: dict, flow: dict, auth_response: dict) -> dict:
    """Exchange the auth-code response for tokens; returns the id_token_claims dict."""
    result = _app(cfg).acquire_token_by_auth_code_flow(flow, auth_response)
    if "error" in result:
        raise ValueError(result.get("error_description") or result["error"])
    return result["id_token_claims"]
