"""Chat turn lifecycle integration tests (017 US3). Per-test isolated DB."""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository
from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _seed_session(name="Session") -> str:
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
        return sess.chat_session_id


# --------------------------------------------------------------------------- turn submission
def test_submit_turn_creates_turn_in_db(client, monkeypatch) -> None:
    sid = _seed_session()
    # Patch run_turn to be a no-op (avoid real HTTP)
    monkeypatch.setattr(
        "harness.ui.chat_session.routes.run_turn",
        lambda *args, **kwargs: None,
    )
    resp = client.post(f"/chat/sessions/{sid}/turns", json={"message": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert "turn_id" in body

    with get_session() as db:
        repo = ChatSessionRepository(db)
        turn = repo.get_turn(body["turn_id"], sid)
        assert turn is not None
        assert turn.status == "in_progress"
        assert turn.user_message == "hello"


def test_submit_turn_409_when_already_in_progress(client, monkeypatch) -> None:
    sid = _seed_session()
    monkeypatch.setattr(
        "harness.ui.chat_session.routes.run_turn",
        lambda *args, **kwargs: None,
    )
    client.post(f"/chat/sessions/{sid}/turns", json={"message": "first"})
    resp = client.post(f"/chat/sessions/{sid}/turns", json={"message": "second"})
    assert resp.status_code == 409


def test_submit_turn_returns_json_turn_id(client, monkeypatch) -> None:
    sid = _seed_session()
    monkeypatch.setattr(
        "harness.ui.chat_session.routes.run_turn",
        lambda *args, **kwargs: None,
    )
    resp = client.post(f"/chat/sessions/{sid}/turns", json={"message": "hi"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["turn_id"], str)
    assert len(data["turn_id"]) > 0


def test_submit_turn_404_for_unknown_session(client) -> None:
    resp = client.post("/chat/sessions/no-such-session/turns", json={"message": "hi"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- turn repository
def test_get_in_progress_turn_returns_active_turn() -> None:
    with get_session() as db:
        cid = ConnectorRegistrationRepository(db).create({
            "display_name": "C", "endpoint_url": "https://c.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 30,
            "expects_per_row_password": False, "supports_sse": True,
        }).connector_id
        eid = EvaluationAgentRegistrationRepository(db).create({
            "display_name": "E", "description": "e", "endpoint_url": "https://e.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 60,
            "declared_scoring_dimensions": [], "supports_sse": True,
        }).evaluation_agent_id
        from harness.chat.session_service import ChatSessionService
        from harness.chat.turn_service import TurnService
        sess = ChatSessionService(db).create_session("S", cid, "t", "p", eid, "oid-1")
        TurnService(db).create_turn(sess.chat_session_id, "hello")
        turn = ChatSessionRepository(db).get_in_progress_turn(sess.chat_session_id)
        assert turn is not None
        assert turn.status == "in_progress"


def test_recover_stale_turns_marks_in_progress_as_failed() -> None:
    with get_session() as db:
        cid = ConnectorRegistrationRepository(db).create({
            "display_name": "C", "endpoint_url": "https://c.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 30,
            "expects_per_row_password": False, "supports_sse": True,
        }).connector_id
        eid = EvaluationAgentRegistrationRepository(db).create({
            "display_name": "E", "description": "e", "endpoint_url": "https://e.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 60,
            "declared_scoring_dimensions": [], "supports_sse": True,
        }).evaluation_agent_id
        from harness.chat.session_service import ChatSessionService
        from harness.chat.turn_service import TurnService
        sess = ChatSessionService(db).create_session("S", cid, "t", "p", eid, "oid-1")
        turn = TurnService(db).create_turn(sess.chat_session_id, "hi")
        turn_id = turn.turn_id
        session_id = sess.chat_session_id

    with get_session() as db:
        repo = ChatSessionRepository(db)
        recovered = repo.recover_stale_turns()
        assert recovered >= 1
        t = repo.get_turn(turn_id, session_id)
        assert t.status == "failed"
        assert t.result is not None
        assert "restarted" in (t.result.error_details or "").lower()
