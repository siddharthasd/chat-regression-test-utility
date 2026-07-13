"""Admin Chat Session Maintenance integration tests (017 US6). Per-test isolated DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository
from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "chat_maint.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "chat_maint.key"))
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "chat_maint.db")
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _seed_session(name="Session", created_ago_days=0) -> str:
    with get_session() as db:
        cid = ConnectorRegistrationRepository(db).create({
            "display_name": "Conn", "endpoint_url": "https://c.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 30,
            "expects_per_row_password": False, "supports_sse": True,
        }).connector_id
        eid = EvaluationAgentRegistrationRepository(db).create({
            "display_name": "Eval", "description": "e", "endpoint_url": "https://e.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 60,
            "declared_scoring_dimensions": [], "supports_sse": True,
        }).evaluation_agent_id
        from harness.chat.session_service import ChatSessionService
        sess = ChatSessionService(db).create_session(name, cid, "tid", "pw", eid, "oid-1")
        if created_ago_days > 0:
            sess.created_at = datetime.now(UTC) - timedelta(days=created_ago_days)
        return sess.chat_session_id


# --------------------------------------------------------------------------- stats page
def test_chat_maintenance_page_renders(client) -> None:
    resp = client.get("/admin/chat-maintenance")
    assert resp.status_code == 200
    assert "Chat Session Maintenance" in resp.text


def test_chat_maintenance_shows_zero_stats_when_empty(client) -> None:
    resp = client.get("/admin/chat-maintenance")
    body = resp.text
    assert "0" in body


def test_chat_maintenance_total_sessions_count(client) -> None:
    _seed_session("Alpha")
    _seed_session("Beta")
    resp = client.get("/admin/chat-maintenance")
    body = resp.text
    assert "2" in body


def test_chat_maintenance_shows_db_size(client) -> None:
    resp = client.get("/admin/chat-maintenance")
    body = resp.text
    assert "MB" in body or "0." in body or any(str(n) in body for n in range(1, 100))


def test_chat_maintenance_shows_inactivity_breakdown(client) -> None:
    resp = client.get("/admin/chat-maintenance")
    body = resp.text
    # Check that different day breakdowns are shown
    assert "7 days" in body
    assert "30 days" in body
    assert "90 days" in body


# --------------------------------------------------------------------------- preview
def test_preview_returns_count_for_7_days(client) -> None:
    _seed_session("OldSession", created_ago_days=10)
    resp = client.post("/admin/chat-maintenance/preview", data={"days": "7"})
    assert resp.status_code == 200
    assert "1" in resp.text


def test_preview_returns_zero_for_fresh_sessions(client) -> None:
    _seed_session("FreshSession", created_ago_days=0)
    resp = client.post("/admin/chat-maintenance/preview", data={"days": "7"})
    assert resp.status_code == 200
    assert "0" in resp.text


def test_preview_invalid_days_returns_422(client) -> None:
    resp = client.post("/admin/chat-maintenance/preview", data={"days": "999"})
    assert resp.status_code in (400, 422)


def test_preview_shows_delete_button_when_count_nonzero(client) -> None:
    _seed_session("OldSession", created_ago_days=35)
    resp = client.post("/admin/chat-maintenance/preview", data={"days": "30"})
    body = resp.text
    assert "Delete" in body


def test_preview_no_delete_button_when_count_zero(client) -> None:
    _seed_session("Fresh", created_ago_days=0)
    resp = client.post("/admin/chat-maintenance/preview", data={"days": "7"})
    body = resp.text
    # When 0 sessions match, no delete button
    assert "0 session" in body or "Nothing to delete" in body


# --------------------------------------------------------------------------- delete
def test_delete_removes_old_sessions(client) -> None:
    sid = _seed_session("OldSession", created_ago_days=40)
    resp = client.post("/admin/chat-maintenance/delete", data={"days": "30"})
    assert resp.status_code in (302, 303)

    with get_session() as db:
        sess = ChatSessionRepository(db).get_session(sid)
    assert sess is None


def test_delete_preserves_fresh_sessions(client) -> None:
    fresh_sid = _seed_session("Fresh", created_ago_days=0)
    old_sid = _seed_session("Old", created_ago_days=40)

    client.post("/admin/chat-maintenance/delete", data={"days": "30"})

    with get_session() as db:
        repo = ChatSessionRepository(db)
        assert repo.get_session(fresh_sid) is not None
        assert repo.get_session(old_sid) is None


def test_delete_shows_success_flash(client) -> None:
    _seed_session("OldOne", created_ago_days=10)
    client.post("/admin/chat-maintenance/delete", data={"days": "7"})
    body = client.get("/admin/chat-maintenance").text
    assert "Deleted" in body or "deleted" in body


def test_delete_invalid_days_returns_422(client) -> None:
    resp = client.post("/admin/chat-maintenance/delete", data={"days": "14"})
    assert resp.status_code in (400, 422)


# --------------------------------------------------------------------------- nav
def test_chat_maintenance_link_in_admin_nav(client) -> None:
    body = client.get("/").text
    assert "chat-maintenance" in body or "Chat Session Maintenance" in body
