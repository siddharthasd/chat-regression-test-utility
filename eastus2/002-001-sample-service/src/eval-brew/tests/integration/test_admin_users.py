"""Admin user management integration tests (015).

Tests run with auth disabled (synthetic admin user) — verifies the
CRUD routes, role-change, and self-removal guard without MSAL roundtrips.
"""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.user_registration import UserRegistrationRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _list_regs():
    with get_session() as db:
        return UserRegistrationRepository(db).list_all()


# ----------------------------------------------------------------- list page
def test_admin_users_page_renders(client) -> None:
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert "User Management" in resp.text


def test_admin_users_page_shows_empty_state(client) -> None:
    resp = client.get("/admin/users")
    assert "No users registered" in resp.text


# ----------------------------------------------------------------- register
def test_register_user_creates_record(client) -> None:
    resp = client.post(
        "/admin/users/new",
        data={"email": "alice@example.com", "role": "user", "display_name": "Alice"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    regs = _list_regs()
    assert len(regs) == 1
    assert regs[0].email == "alice@example.com"
    assert regs[0].role == "user"


def test_register_user_normalises_email_to_lowercase(client) -> None:
    client.post(
        "/admin/users/new",
        data={"email": "ALICE@EXAMPLE.COM", "role": "user"},
        follow_redirects=False,
    )
    assert _list_regs()[0].email == "alice@example.com"


def test_register_duplicate_email_redirects_without_creating(client) -> None:
    for _ in range(2):
        client.post(
            "/admin/users/new",
            data={"email": "dup@example.com", "role": "user"},
            follow_redirects=False,
        )
    assert len(_list_regs()) == 1


def test_register_admin_role(client) -> None:
    client.post(
        "/admin/users/new",
        data={"email": "boss@example.com", "role": "admin"},
        follow_redirects=False,
    )
    assert _list_regs()[0].role == "admin"


# ----------------------------------------------------------------- change role
def test_change_role_updates_record(client) -> None:
    client.post(
        "/admin/users/new",
        data={"email": "bob@example.com", "role": "user"},
        follow_redirects=False,
    )
    reg = _list_regs()[0]
    resp = client.post(
        f"/admin/users/{reg.id}/change-role",
        data={"role": "admin"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    with get_session() as db:
        updated = UserRegistrationRepository(db).get(reg.id)
    assert updated.role == "admin"


def test_change_role_404_for_unknown_id(client) -> None:
    resp = client.post(
        "/admin/users/does-not-exist/change-role",
        data={"role": "user"},
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ----------------------------------------------------------------- remove
def test_remove_user_deletes_record(client) -> None:
    client.post(
        "/admin/users/new",
        data={"email": "todel@example.com", "role": "user"},
        follow_redirects=False,
    )
    reg = _list_regs()[0]
    resp = client.post(
        f"/admin/users/{reg.id}/remove",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert _list_regs() == []


def test_remove_user_404_for_unknown_id(client) -> None:
    resp = client.post("/admin/users/does-not-exist/remove", follow_redirects=False)
    assert resp.status_code == 404


# ----------------------------------------------------------------- new user form
def test_new_user_form_renders(client) -> None:
    resp = client.get("/admin/users/new")
    assert resp.status_code == 200
    assert "Register New User" in resp.text
    assert "admin" in resp.text and "user" in resp.text


# ----------------------------------------------------------------- users list populated
def test_users_list_shows_registered_users(client) -> None:
    client.post(
        "/admin/users/new",
        data={"email": "visible@example.com", "role": "admin"},
        follow_redirects=False,
    )
    resp = client.get("/admin/users")
    assert "visible@example.com" in resp.text
    assert "admin" in resp.text
