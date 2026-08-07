"""Azure AD OAuth2 auth routes — login / callback / logout / unauthorised (015)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

import harness.auth.msal_client as msal_client
from harness.auth.config import get_auth_config
from harness.auth.session import (
    clear_auth_flow,
    clear_session_user,
    get_auth_flow,
    get_session_user,
    set_auth_flow,
    set_session_user,
)
from harness.persistence import get_session
from harness.persistence.repositories.user_registration import UserRegistrationRepository
from harness.ui._context import ctx
from harness.ui._templates import templates

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/auth/login", name="login")
def login(request: Request):
    log.debug("sso.login.initiated")
    cfg = get_auth_config()
    flow = msal_client.initiate_flow(cfg)
    set_auth_flow(request, flow)
    log.debug("sso.login.redirecting_to_azure")
    return RedirectResponse(flow["auth_uri"], status_code=302)


@router.get("/auth/callback", name="auth_callback")
def auth_callback(request: Request):
    log.debug("sso.callback.received")
    cfg = get_auth_config()
    flow = get_auth_flow(request)
    clear_auth_flow(request)

    if flow is None:
        log.debug("sso.callback.no_flow_in_session")
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {"message": "Auth session expired. Please try logging in again.", **ctx(request)},
            status_code=400,
        )

    try:
        claims = msal_client.complete_flow(cfg, flow, dict(request.query_params))
    except (ValueError, KeyError) as exc:
        log.debug("sso.callback.flow_failed", error=str(exc)[:200])
        return templates.TemplateResponse(
            request,
            "auth/error.html",
            {"message": str(exc), **ctx(request)},
            status_code=400,
        )

    oid = claims.get("oid") or claims.get("sub")
    display_name = claims.get("name") or ""

    # Build a priority-ordered list of email candidates from the OIDC token.
    # In Accenture's federated SSO, Azure AD may surface the user's address in
    # different claims depending on tenant and app-registration configuration:
    #   preferred_username – OIDC standard (v2.0 tokens)
    #   userprincipalname  – UPN attribute surfaced directly by the SSO provider
    #   email              – explicit SMTP claim (requires the "email" scope)
    #   upn                – UPN emitted explicitly by some ADFS federations
    #   unique_name        – UPN in Azure AD v1.0 / ADFS tokens (ver=1.0)
    #   name               – display name fallback (filtered if no @ present)
    _raw = [
        claims.get("preferred_username"),
        claims.get("userprincipalname"),
        claims.get("email"),
        claims.get("upn"),
        claims.get("unique_name"),
        claims.get("name"),
    ]
    seen: set[str] = set()
    email_candidates: list[str] = []
    for c in _raw:
        if c and "@" in c:
            lowered = c.lower()
            if lowered not in seen:
                seen.add(lowered)
                email_candidates.append(lowered)

    log.debug("sso.callback.claims_resolved", oid=oid, email_candidates=len(email_candidates))

    with get_session() as db:
        repo = UserRegistrationRepository(db)
        reg = repo.find_by_oid(oid)
        if reg is None:
            # First login (azure_oid IS NULL): one IN query across all email
            # candidates — handles the Accenture case where preferred_username /
            # UPN differs from the SMTP address the admin used to pre-register.
            reg = repo.find_unlinked_by_any_email(email_candidates)
            if reg is not None:
                log.debug("sso.callback.oid_linked", oid=oid, email=reg.email)
                repo.link_oid(reg, oid, display_name or reg.email)
        if reg is None:
            # Final fallback: search by email without the azure_oid IS NULL
            # constraint. Covers users whose record already has an OID linked
            # from a previous session but whose current token carries a different
            # OID (account recreation, tenant migration, or multi-environment
            # first-login mismatch). Re-link to the new OID so the user is not
            # permanently locked out.
            reg = repo.find_by_any_email(email_candidates)
            if reg is not None:
                log.debug("sso.callback.oid_relinked", oid=oid, email=reg.email,
                          previous_oid=reg.azure_oid)
                repo.link_oid(reg, oid, display_name or reg.email)
        if reg is None:
            log.debug("sso.callback.not_registered", oid=oid)
            return RedirectResponse(request.url_for("unauthorised"), status_code=302)
        repo.update_last_login(reg)
        role = reg.role
        # Use the canonical email from the DB (the address the admin registered),
        # not whichever token claim happened to match during the lookup above.
        canonical_email = reg.email

    display_name = display_name or canonical_email
    log.debug("sso.callback.session_established", oid=oid, email=canonical_email, role=role)
    set_session_user(request, oid=oid, email=canonical_email, display_name=display_name, role=role)
    next_url = request.session.pop("next", None) or str(request.url_for("index"))
    return RedirectResponse(next_url, status_code=302)


@router.post("/auth/logout", name="logout")
def logout(request: Request):
    user = get_session_user(request)
    log.debug("sso.logout.initiated", oid=user.get("oid") if user else None)
    clear_session_user(request)
    request.session.clear()
    cfg = get_auth_config()
    tenant_id = cfg.get("tenant_id", "common")
    client_id = cfg.get("client_id", "")
    post_logout = str(request.url_for("index"))
    azure_logout = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/logout"
        f"?client_id={client_id}&post_logout_redirect_uri={post_logout}"
    )
    log.debug("sso.logout.redirecting_to_azure")
    return RedirectResponse(azure_logout, status_code=302)


@router.get("/auth/unauthorised", name="unauthorised")
def unauthorised(request: Request):
    return templates.TemplateResponse(
        request,
        "auth/unauthorised.html",
        ctx(request),
        status_code=403,
    )
