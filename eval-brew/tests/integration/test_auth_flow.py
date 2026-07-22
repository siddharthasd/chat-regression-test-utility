"""Auth flow integration tests (015).

These tests verify the FastAPI auth routes, session management, and role
enforcement WITHOUT hitting Azure AD — MSAL is monkeypatched throughout.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.user_registration import UserRegistrationRepository


_FAKE_OID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_FAKE_EMAIL = "tester@example.com"
_FAKE_NAME = "Test User"

_FAKE_FLOW = {
    "auth_uri": "https://login.microsoftonline.com/fake/oauth2/authorize?code=stub",
    "state": "fakestate",
    "code_verifier": "fakeverifier",
    "nonce": "fakenonce",
    "scope": ["openid", "profile", "email"],
}

_FAKE_CLAIMS = {
    "oid": _FAKE_OID,
    "preferred_username": _FAKE_EMAIL,
    "name": _FAKE_NAME,
}

# Simulates Accenture federated SSO where preferred_username (UPN) differs
# from the SMTP address the admin pre-registered.
_FAKE_CLAIMS_UPN_MISMATCH = {
    "oid": _FAKE_OID,
    "preferred_username": "john.doe@accentureinternal.onmicrosoft.com",
    "email": _FAKE_EMAIL,
    "name": _FAKE_NAME,
}

# Only upn / unique_name claims carry the matching address.
_FAKE_CLAIMS_LEGACY_CLAIM = {
    "oid": _FAKE_OID,
    "preferred_username": "john.doe@accentureinternal.onmicrosoft.com",
    "upn": _FAKE_EMAIL,
    "name": _FAKE_NAME,
}


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """TestClient with HARNESS_AUTH_ENABLED=true and MSAL patched."""
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "auth.key"))
    monkeypatch.setenv("HARNESS_AUTH_ENABLED", "true")
    monkeypatch.setenv("HARNESS_AZURE_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("HARNESS_AZURE_CLIENT_ID", "fake-client")
    monkeypatch.setenv("HARNESS_AZURE_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("HARNESS_SESSION_SECRET", "test-secret-key-32-bytes-xxxxxxxxx")
    monkeypatch.setenv("HARNESS_REDIRECT_URI", "http://localhost/auth/callback")

    import harness.ui.auth.routes as auth_routes_mod

    monkeypatch.setattr(auth_routes_mod.msal_client, "initiate_flow", lambda cfg: _FAKE_FLOW)
    monkeypatch.setattr(auth_routes_mod.msal_client, "complete_flow", lambda cfg, flow, resp: _FAKE_CLAIMS)

    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "auth.db")
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


@pytest.fixture
def noauth_client(tmp_path, monkeypatch):
    """TestClient with auth disabled — all routes accessible as synthetic admin."""
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "noauth.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "noauth.key"))
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "noauth.db")
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


# ----------------------------------------------------------------- auth disabled

def test_dashboard_accessible_without_auth(noauth_client) -> None:
    resp = noauth_client.get("/")
    assert resp.status_code == 200


def test_admin_routes_accessible_without_auth(noauth_client) -> None:
    resp = noauth_client.get("/admin/users")
    assert resp.status_code == 200


# ----------------------------------------------------------------- auth enabled: redirect to login

def test_unauthenticated_request_redirects_to_login(auth_client) -> None:
    resp = auth_client.get("/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


def test_login_route_redirects_to_azure(auth_client) -> None:
    resp = auth_client.get("/auth/login")
    assert resp.status_code == 302
    assert "login.microsoftonline.com" in resp.headers["location"]


def test_unauthorised_page_renders(auth_client) -> None:
    resp = auth_client.get("/auth/unauthorised")
    assert resp.status_code == 403
    assert "Access Denied" in resp.text


# ----------------------------------------------------------------- callback: unregistered user

def test_callback_unregistered_user_redirects_to_unauthorised(auth_client) -> None:
    # Seed the session with a flow so callback doesn't 400
    with auth_client as c:
        # Manually set auth_flow in session via login route first
        login_resp = c.get("/auth/login")
        assert login_resp.status_code == 302
        # Now hit callback — fake complete_flow returns claims, but no registration exists
        cb_resp = c.get("/auth/callback?code=stub&state=fakestate")
        assert cb_resp.status_code == 302
        assert "unauthorised" in cb_resp.headers["location"]


# ----------------------------------------------------------------- callback: registered user

def _register_user(role: str = "user") -> None:
    with get_session() as db:
        UserRegistrationRepository(db).create(
            email=_FAKE_EMAIL, role=role, display_name=_FAKE_NAME
        )


def test_callback_registered_user_redirects_to_dashboard(auth_client) -> None:
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        cb_resp = c.get("/auth/callback?code=stub&state=fakestate")
        assert cb_resp.status_code == 302
        assert cb_resp.headers["location"].endswith("/")


def test_callback_links_oid_on_first_login(auth_client) -> None:
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
    with get_session() as db:
        reg = UserRegistrationRepository(db).find_by_email(_FAKE_EMAIL)
    assert reg.azure_oid == _FAKE_OID


def test_callback_updates_last_login(auth_client) -> None:
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
    with get_session() as db:
        reg = UserRegistrationRepository(db).find_by_email(_FAKE_EMAIL)
    assert reg.last_login_at is not None


def test_authenticated_user_can_access_dashboard(auth_client) -> None:
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        cb = c.get("/auth/callback?code=stub&state=fakestate")
        assert cb.status_code == 302
        resp = c.get("/", follow_redirects=True)
    assert resp.status_code == 200


# ----------------------------------------------------------------- role enforcement

def test_user_role_cannot_access_admin_page(auth_client) -> None:
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
        resp = c.get("/admin/users", follow_redirects=True)
    assert resp.status_code == 403


def test_admin_role_can_access_admin_page(auth_client) -> None:
    _register_user(role="admin")
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
        resp = c.get("/admin/users", follow_redirects=True)
    assert resp.status_code == 200


# ----------------------------------------------------------------- logout

# --------- SSO email-claim fallback (Accenture federated UPN vs SMTP address)

def test_callback_falls_back_to_email_claim_when_upn_differs(auth_client, monkeypatch) -> None:
    """User is pre-registered with SMTP address; UPN in preferred_username differs."""
    import harness.ui.auth.routes as auth_routes_mod

    monkeypatch.setattr(
        auth_routes_mod.msal_client,
        "complete_flow",
        lambda cfg, flow, resp: _FAKE_CLAIMS_UPN_MISMATCH,
    )
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        cb = c.get("/auth/callback?code=stub&state=fakestate")
    assert cb.status_code == 302
    assert "unauthorised" not in cb.headers["location"]


def test_callback_falls_back_to_upn_claim(auth_client, monkeypatch) -> None:
    """Matching address is in the explicit upn claim, not preferred_username."""
    import harness.ui.auth.routes as auth_routes_mod

    monkeypatch.setattr(
        auth_routes_mod.msal_client,
        "complete_flow",
        lambda cfg, flow, resp: _FAKE_CLAIMS_LEGACY_CLAIM,
    )
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        cb = c.get("/auth/callback?code=stub&state=fakestate")
    assert cb.status_code == 302
    assert "unauthorised" not in cb.headers["location"]


def test_callback_session_email_is_canonical_db_email(auth_client, monkeypatch) -> None:
    """Session stores the DB-canonical email, not the token UPN.

    After login via the email-claim fallback the user's admin page shows the
    pre-registered SMTP address, confirming the session was built from the DB
    record rather than from the token's preferred_username (UPN).
    """
    import harness.ui.auth.routes as auth_routes_mod

    monkeypatch.setattr(
        auth_routes_mod.msal_client,
        "complete_flow",
        lambda cfg, flow, resp: _FAKE_CLAIMS_UPN_MISMATCH,
    )
    _register_user(role="admin")  # admin role so /admin/users is accessible
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
        # /admin/users renders reg.email for every registered user — the
        # canonical SMTP address must appear, NOT the mismatched UPN.
        resp = c.get("/admin/users", follow_redirects=True)
    assert resp.status_code == 200
    assert _FAKE_EMAIL in resp.text
    assert "accentureinternal.onmicrosoft.com" not in resp.text


def test_callback_links_oid_via_email_claim_fallback(auth_client, monkeypatch) -> None:
    """OID is correctly linked to the record found via the email claim fallback."""
    import harness.ui.auth.routes as auth_routes_mod

    monkeypatch.setattr(
        auth_routes_mod.msal_client,
        "complete_flow",
        lambda cfg, flow, resp: _FAKE_CLAIMS_UPN_MISMATCH,
    )
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
    with get_session() as db:
        reg = UserRegistrationRepository(db).find_by_email(_FAKE_EMAIL)
    assert reg.azure_oid == _FAKE_OID


# ----------------------------------------------------------------- logout

def test_logout_clears_session_and_redirects_to_azure(auth_client) -> None:
    _register_user(role="user")
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
        # confirm logged in
        assert c.get("/", follow_redirects=True).status_code == 200
        # log out
        logout_resp = c.post("/auth/logout")
        assert logout_resp.status_code == 302
        assert "login.microsoftonline.com" in logout_resp.headers["location"]
        # confirm session cleared — dashboard should redirect to login
        assert c.get("/").status_code == 302
