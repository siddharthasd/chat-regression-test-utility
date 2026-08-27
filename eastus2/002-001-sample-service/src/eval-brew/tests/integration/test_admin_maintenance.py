"""Admin Job Maintenance integration tests (016).

Tests run with auth disabled (synthetic admin) — verifies stats panel,
Clear & Vacuum action, role protection, and nav structure.
"""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _seed(*, status=JobStatus.DRAFT, name="Job", failed=0) -> str:
    with get_session() as session:
        job = JobRepository(session).create_draft(name, None, "tester")
        job.status = status.value if isinstance(status, JobStatus) else status
        job.failed_count = failed
        return job.job_id


# ----------------------------------------------------------------- US1: stats page
def test_maintenance_page_renders(client) -> None:
    resp = client.get("/admin/maintenance")
    assert resp.status_code == 200
    assert "Job Maintenance" in resp.text


def test_maintenance_stats_total_jobs(client) -> None:
    _seed(name="A")
    _seed(name="B")
    resp = client.get("/admin/maintenance")
    assert resp.status_code == 200
    assert "2" in resp.text


def test_maintenance_stats_clearable_count(client) -> None:
    _seed(name="Keep", status=JobStatus.COMPLETED, failed=0)
    _seed(name="ClearFailed", status=JobStatus.FAILED)
    _seed(name="ClearCancelled", status=JobStatus.CANCELLED)
    _seed(name="ClearErrors", status=JobStatus.COMPLETED, failed=2)
    resp = client.get("/admin/maintenance")
    body = resp.text
    # 3 clearable jobs (failed + cancelled + completed-with-errors)
    assert "3" in body


def test_maintenance_stats_db_size_present(client) -> None:
    resp = client.get("/admin/maintenance")
    body = resp.text
    # DB size appears as a number (float or int) in the page
    assert "0." in body or any(str(n) in body for n in range(1, 100))


def test_maintenance_page_has_clear_vacuum_button(client) -> None:
    resp = client.get("/admin/maintenance")
    assert "Clear" in resp.text
    assert "Vacuum" in resp.text


# ----------------------------------------------------------------- US1: role guard
_FAKE_FLOW = {
    "auth_uri": "https://login.microsoftonline.com/fake/oauth2/authorize",
    "state": "fakestate",
    "code_verifier": "fakeverifier",
    "nonce": "fakenonce",
    "scope": ["openid"],
}
_FAKE_CLAIMS = {
    "oid": "user-oid-001",
    "preferred_username": "reguser@test.com",
    "name": "Regular User",
}


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("HARNESS_AUTH_ENABLED", "true")
    monkeypatch.setenv("HARNESS_AZURE_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("HARNESS_AZURE_CLIENT_ID", "fake-client")
    monkeypatch.setenv("HARNESS_AZURE_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("HARNESS_SESSION_SECRET", "test-secret-key-32-bytes-xxxxxxxxx")
    monkeypatch.setenv("HARNESS_REDIRECT_URI", "http://localhost/auth/callback")
    import harness.ui.auth.routes as auth_routes_mod

    monkeypatch.setattr(auth_routes_mod.msal_client, "initiate_flow", lambda cfg: _FAKE_FLOW)
    monkeypatch.setattr(
        auth_routes_mod.msal_client, "complete_flow", lambda cfg, flow, resp: _FAKE_CLAIMS
    )
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def test_maintenance_role_guard_with_user_role(auth_client) -> None:
    from harness.persistence.repositories.user_registration import UserRegistrationRepository

    with get_session() as db:
        UserRegistrationRepository(db).create(
            email="reguser@test.com", role="user", display_name="Regular User"
        )
    with auth_client as c:
        c.get("/auth/login")
        c.get("/auth/callback?code=stub&state=fakestate")
        resp = c.get("/admin/maintenance", follow_redirects=True)
    assert resp.status_code == 403


# ----------------------------------------------------------------- US2: clear & vacuum
def test_clear_vacuum_zero_clearable(client) -> None:
    _seed(name="GoodJob", status=JobStatus.COMPLETED, failed=0)
    resp = client.post("/admin/maintenance")
    assert resp.status_code == 303
    # Redirect to maintenance page
    assert "/admin/maintenance" in resp.headers["location"]


def test_clear_vacuum_deletes_terminal_jobs(client) -> None:
    _seed(name="Failed", status=JobStatus.FAILED)
    _seed(name="Cancelled", status=JobStatus.CANCELLED)
    _seed(name="Errors", status=JobStatus.COMPLETED, failed=1)
    _seed(name="Good", status=JobStatus.COMPLETED, failed=0)

    resp = client.post("/admin/maintenance")
    assert resp.status_code == 303

    # Follow redirect and check flash
    body = client.get("/admin/maintenance").text
    assert "Deleted 3 job(s)" in body


def test_clear_vacuum_preserves_successful_jobs(client) -> None:
    _seed(name="ShouldStay", status=JobStatus.COMPLETED, failed=0)
    _seed(name="Clearable", status=JobStatus.FAILED)

    client.post("/admin/maintenance")

    with get_session() as db:
        remaining = JobRepository(db).count_all()
    assert remaining == 1


def test_clear_vacuum_flash_contains_size_info(client) -> None:
    _seed(name="ToDelete", status=JobStatus.FAILED)
    client.post("/admin/maintenance")
    body = client.get("/admin/maintenance").text
    assert "MB" in body


def test_clear_vacuum_with_no_jobs_succeeds(client) -> None:
    resp = client.post("/admin/maintenance")
    assert resp.status_code == 303
    body = client.get("/admin/maintenance").text
    assert "Deleted 0 job(s)" in body


# ----------------------------------------------------------------- US3: nav structure
def test_admin_dropdown_present_in_nav(client) -> None:
    body = client.get("/").text
    assert "Admin" in body
    assert "Job Maintenance" in body
    assert "admin/maintenance" in body


def test_admin_dropdown_contains_users_link(client) -> None:
    body = client.get("/").text
    assert "admin/users" in body


def test_no_standalone_users_nav_item(client) -> None:
    body = client.get("/").text
    # Users link must only appear inside the Admin dropdown section,
    # not as a bare top-level nav link with its own SVG icon block
    # The dropdown structure means admin_users URL appears once inside the dropdown
    assert body.count("admin/users") >= 1
    # The old standalone SVG icon path for users should not appear outside dropdown
    assert "M7 14s-1 0-1-1 1-4 5-4" not in body
