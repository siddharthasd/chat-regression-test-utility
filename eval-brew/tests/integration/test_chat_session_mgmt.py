"""Chat session management integration tests (017 US2/US4/US5). Per-test isolated DB."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository
from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "mgmt.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "mgmt.key"))
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "mgmt.db")
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _seed_session(name="Test Session", owner_oid="oid-alice") -> str:
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
        sess = ChatSessionService(db).create_session(name, cid, "tid", "pw", eid, owner_oid)
        return sess.chat_session_id


# --------------------------------------------------------------------------- session list
def test_session_list_renders(client) -> None:
    resp = client.get("/chat/sessions")
    assert resp.status_code == 200


def test_session_list_shows_session_names(client) -> None:
    _seed_session("AlphaSession")
    _seed_session("BetaSession")
    resp = client.get("/chat/sessions")
    assert "AlphaSession" in resp.text
    assert "BetaSession" in resp.text


def test_session_list_empty_state(client) -> None:
    resp = client.get("/chat/sessions")
    assert resp.status_code == 200
    # Should not crash; some indication of no sessions
    assert "session" in resp.text.lower()


def test_session_list_has_new_session_link(client) -> None:
    body = client.get("/chat/sessions").text
    assert "wizard" in body or "New" in body


# --------------------------------------------------------------------------- chat interface
def test_chat_interface_renders(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}")
    assert resp.status_code == 200
    assert "chat" in resp.text.lower() or "message" in resp.text.lower()


def test_chat_interface_404_for_missing_session(client) -> None:
    resp = client.get("/chat/sessions/no-such-session-id")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- export
def test_export_json_empty_session(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/export?format=json")
    assert resp.status_code == 200
    assert "json" in resp.headers.get("content-type", "")


def test_export_csv_empty_session(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/export?format=csv")
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "") or "text" in resp.headers.get("content-type", "")


def test_export_json_contains_session_name(client) -> None:
    import json as json_mod
    sid = _seed_session("ExportSession")
    resp = client.get(f"/chat/sessions/{sid}/export?format=json")
    payload = json_mod.loads(resp.content)
    assert payload["session"]["session_name"] == "ExportSession"


def test_export_json_excludes_credentials(client) -> None:
    import json as json_mod
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/export?format=json")
    payload = json_mod.loads(resp.content)
    raw = resp.text
    assert "test_id_enc" not in raw
    assert "test_password_enc" not in raw
    assert "tid" not in raw  # plaintext test_id must not appear
    assert "pw" not in raw   # plaintext password must not appear


def test_export_unknown_format_returns_400(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/export?format=xml")
    assert resp.status_code in (400, 422)


# --------------------------------------------------------------------------- delete
def test_delete_session_redirects(client) -> None:
    sid = _seed_session()
    resp = client.post(f"/chat/sessions/{sid}/delete?confirm=true")
    assert resp.status_code in (302, 303)


def test_delete_session_removes_from_db(client) -> None:
    sid = _seed_session()
    client.post(f"/chat/sessions/{sid}/delete?confirm=true")

    with get_session() as db:
        sess = ChatSessionRepository(db).get_session(sid)
    assert sess is None


def test_delete_session_not_found_returns_404(client) -> None:
    resp = client.post("/chat/sessions/no-such-session/delete?confirm=true")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- dashboard integration
def test_dashboard_shows_chat_sessions_section(client) -> None:
    _seed_session("DashSession")
    body = client.get("/").text
    assert "Chat Sessions" in body
    assert "DashSession" in body
