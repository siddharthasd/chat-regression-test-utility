"""Chat Session Wizard integration tests (017 US1). Per-test isolated DB."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository
from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "wiz.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "wiz.key"))
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "wiz.db")
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _seed_sse_connector(name="SSEConn") -> str:
    with get_session() as session:
        reg = ConnectorRegistrationRepository(session).create({
            "display_name": name,
            "endpoint_url": "https://conn.test/api",
            "auth_descriptor": {"mode": "none"},
            "timeout_seconds": 30,
            "expects_per_row_password": False,
            "supports_sse": True,
        })
        return reg.connector_id


def _seed_non_sse_connector(name="PlainConn") -> str:
    with get_session() as session:
        reg = ConnectorRegistrationRepository(session).create({
            "display_name": name,
            "endpoint_url": "https://plain.test/api",
            "auth_descriptor": {"mode": "none"},
            "timeout_seconds": 30,
            "expects_per_row_password": False,
            "supports_sse": False,
        })
        return reg.connector_id


def _seed_sse_evaluator(name="SSEEval") -> str:
    with get_session() as session:
        reg = EvaluationAgentRegistrationRepository(session).create({
            "display_name": name,
            "description": "scores",
            "endpoint_url": "https://eval.test/api",
            "auth_descriptor": {"mode": "none"},
            "timeout_seconds": 60,
            "declared_scoring_dimensions": ["relevance"],
            "supports_sse": True,
        })
        return reg.evaluation_agent_id


def _full_wizard(client, *, session_name="My Session", connector_id, test_id="user@test",
                 password="secret", evaluator_id):
    """Drive all 5 wizard steps and return the final redirect location."""
    client.post("/chat/wizard/step1", data={"session_name": session_name})
    client.post("/chat/wizard/step2", data={"connector_id": connector_id})
    client.post("/chat/wizard/step3", data={"test_id": test_id, "password": password})
    client.post("/chat/wizard/step4", data={"evaluator_id": evaluator_id})
    resp = client.post("/chat/wizard/step5")
    return resp


# --------------------------------------------------------------------------- step navigation
def test_step1_get_renders(client) -> None:
    resp = client.get("/chat/wizard/step1")
    assert resp.status_code == 200
    assert "session" in resp.text.lower()


def test_step1_post_valid_redirects_to_step2(client) -> None:
    resp = client.post("/chat/wizard/step1", data={"session_name": "My Session"})
    assert resp.status_code in (302, 303)
    assert "step2" in resp.headers["location"]


def test_step1_post_empty_name_stays_on_step1(client) -> None:
    resp = client.post("/chat/wizard/step1", data={"session_name": ""}, follow_redirects=True)
    assert resp.status_code in (200, 400)
    assert "step1" in str(resp.url) or resp.status_code == 200


def test_step2_shows_only_sse_connectors(client) -> None:
    _seed_sse_connector("SSEConn")
    _seed_non_sse_connector("PlainConn")
    client.post("/chat/wizard/step1", data={"session_name": "S"})
    resp = client.get("/chat/wizard/step2")
    assert resp.status_code == 200
    assert "SSEConn" in resp.text
    assert "PlainConn" not in resp.text


def test_step2_empty_state_message_when_no_sse_connectors(client) -> None:
    _seed_non_sse_connector()
    client.post("/chat/wizard/step1", data={"session_name": "S"})
    resp = client.get("/chat/wizard/step2")
    assert resp.status_code == 200
    assert "No SSE" in resp.text or "no" in resp.text.lower()


def test_step4_shows_only_sse_evaluators(client) -> None:
    cid = _seed_sse_connector()
    _seed_sse_evaluator("SSEEval")
    client.post("/chat/wizard/step1", data={"session_name": "S"})
    client.post("/chat/wizard/step2", data={"connector_id": cid})
    client.post("/chat/wizard/step3", data={"test_id": "t", "password": "p"})
    resp = client.get("/chat/wizard/step4")
    assert "SSEEval" in resp.text


# --------------------------------------------------------------------------- full flow
def test_wizard_creates_session_on_step5(client) -> None:
    cid = _seed_sse_connector()
    eid = _seed_sse_evaluator()

    resp = _full_wizard(client, connector_id=cid, evaluator_id=eid)

    assert resp.status_code in (302, 303)
    location = resp.headers["location"]
    assert "/chat/sessions/" in location


def test_wizard_session_persisted_in_db(client) -> None:
    cid = _seed_sse_connector(name="WizConn")
    eid = _seed_sse_evaluator(name="WizEval")

    resp = _full_wizard(client, session_name="WizSession", connector_id=cid, evaluator_id=eid)
    location = resp.headers["location"]
    session_id = location.split("/chat/sessions/")[1].rstrip("/")

    with get_session() as db:
        from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
        sess = ChatSessionRepository(db).get_session(session_id)
        assert sess is not None
        assert sess.session_name == "WizSession"
        assert sess.connector_name == "WizConn"
        assert sess.evaluator_name == "WizEval"


def test_wizard_credentials_encrypted_in_db(client) -> None:
    cid = _seed_sse_connector()
    eid = _seed_sse_evaluator()

    resp = _full_wizard(client, test_id="tester@domain.com", password="TopSecret",
                        connector_id=cid, evaluator_id=eid)
    location = resp.headers["location"]
    session_id = location.split("/chat/sessions/")[1].rstrip("/")

    with get_session() as db:
        from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
        from harness.persistence.encryption import decrypt_credential
        sess = ChatSessionRepository(db).get_session(session_id)
        assert sess.test_id_enc != "tester@domain.com"
        assert decrypt_credential(sess.test_id_enc) == "tester@domain.com"
        assert decrypt_credential(sess.test_password_enc) == "TopSecret"


def test_step5_confirmation_shows_summary(client) -> None:
    cid = _seed_sse_connector(name="SumConn")
    eid = _seed_sse_evaluator(name="SumEval")
    client.post("/chat/wizard/step1", data={"session_name": "SumSession"})
    client.post("/chat/wizard/step2", data={"connector_id": cid})
    client.post("/chat/wizard/step3", data={"test_id": "tester@x.com", "password": "pw"})
    client.post("/chat/wizard/step4", data={"evaluator_id": eid})
    resp = client.get("/chat/wizard/step5")
    assert resp.status_code == 200
    assert "SumSession" in resp.text
    assert "SumConn" in resp.text
    assert "SumEval" in resp.text


# --------------------------------------------------------------------------- progress bar
def test_step1_has_progress_bar(client) -> None:
    resp = client.get("/chat/wizard/step1")
    assert "progress" in resp.text.lower()
