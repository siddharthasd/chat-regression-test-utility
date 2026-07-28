"""Integration tests for live chat analytics (019)."""

from __future__ import annotations

import json as json_mod
import os

import pytest
from starlette.testclient import TestClient

from harness.persistence import get_session
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository
from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "analytics.key"))
    monkeypatch.delenv("HARNESS_AUTH_ENABLED", raising=False)
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    from harness.ui import create_app

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


def _seed_session(name="Analytics Session", owner_oid="oid-alice", dims=None) -> str:
    """Create a session; returns session_id."""
    with get_session() as db:
        cid = ConnectorRegistrationRepository(db).create({
            "display_name": "Conn", "endpoint_url": "https://c.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 30,
            "expects_per_row_password": False, "supports_sse": True,
        }).connector_id
        eid = EvaluationAgentRegistrationRepository(db).create({
            "display_name": "Eval", "description": "e", "endpoint_url": "https://e.test",
            "auth_descriptor": {"mode": "none"}, "timeout_seconds": 60,
            "declared_scoring_dimensions": dims or ["relevance", "tone"],
            "supports_sse": True,
        }).evaluation_agent_id
        from harness.chat.session_service import ChatSessionService
        sess = ChatSessionService(db).create_session(name, cid, "tid", "pw", eid, owner_oid)
        return sess.chat_session_id


def _add_completed_turn(
    session_id: str,
    user_message: str = "Hello?",
    assembled: str = "Hi there.",
    overall_verdict: str = "pass",
    params: list[dict] | None = None,
) -> str:
    """Add a completed turn with evaluation result; returns turn_id."""
    params = params or [
        {"parameter_name": "relevance", "score": 0.9, "reasoning": "good", "verdict": "pass"},
        {"parameter_name": "tone", "score": 0.8, "reasoning": "ok", "verdict": "pass"},
    ]
    final_eval = {"overallVerdict": overall_verdict, "parameters": params}
    with get_session() as db:
        from harness.chat.turn_service import TurnService
        turn_svc = TurnService(db)
        turn = turn_svc.create_turn(session_id, user_message)
        turn_id = turn.turn_id
        repo = ChatSessionRepository(db)
        repo.complete_turn(turn_id, assembled, None, final_eval, [])
    return turn_id


def _add_failed_turn(session_id: str, user_message: str = "Error turn") -> str:
    """Add a failed turn; returns turn_id."""
    with get_session() as db:
        from harness.chat.turn_service import TurnService
        turn_svc = TurnService(db)
        turn = turn_svc.create_turn(session_id, user_message)
        turn_id = turn.turn_id
        repo = ChatSessionRepository(db)
        repo.fail_turn(turn_id, "connector_error", "Connection timed out")
    return turn_id


def _add_in_progress_turn(session_id: str) -> str:
    """Add an in_progress turn (should not appear in analytics or downloads)."""
    with get_session() as db:
        from harness.chat.turn_service import TurnService
        turn = TurnService(db).create_turn(session_id, "In progress message")
        return turn.turn_id


# --------------------------------------------------------------------------- analytics page

def test_analytics_page_renders(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "Analytics" in resp.text
    assert "Session Overview" in resp.text
    assert "Parameter Breakdown" in resp.text
    assert "Turn Explorer" in resp.text


def test_analytics_page_shows_session_name(client) -> None:
    sid = _seed_session("My Chat Session")
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "My Chat Session" in resp.text


def test_analytics_page_empty_session(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "No evaluated results" in resp.text or "0" in resp.text


def test_analytics_page_shows_overall_verdict_distribution(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, overall_verdict="pass")
    _add_completed_turn(sid, overall_verdict="fail")
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "pass" in resp.text.lower()
    assert "fail" in resp.text.lower()


def test_analytics_page_shows_parameter_blocks(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "relevance" in resp.text
    assert "tone" in resp.text


def test_analytics_page_shows_turn_in_explorer(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="What is the weather?")
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "What is the weather?" in resp.text


def test_analytics_page_excludes_in_progress_turns(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="Completed message")
    _add_in_progress_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    # in_progress message must not show in turn explorer
    assert "In progress message" not in resp.text
    assert "Completed message" in resp.text


def test_analytics_includes_failed_turns(client) -> None:
    sid = _seed_session()
    _add_failed_turn(sid, user_message="This will fail")
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "This will fail" in resp.text


def test_analytics_shows_error_status_for_failed_turn(client) -> None:
    sid = _seed_session()
    _add_failed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "connector_error" in resp.text


def test_analytics_has_sidebar_nav(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "sidebar-nav" in resp.text
    assert "section-session-overview" in resp.text
    assert "section-parameter-breakdown" in resp.text
    assert "section-turn-explorer" in resp.text


def test_analytics_has_download_links(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert "download-results.csv" in resp.text
    assert "download-results.json" in resp.text


def test_analytics_404_for_missing_session(client) -> None:
    resp = client.get("/chat/sessions/no-such-session/analytics")
    # returns 403 (owner-scoped, not found means access denied)
    assert resp.status_code in (403, 404)


def test_analytics_has_back_to_session_link(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/analytics")
    assert resp.status_code == 200
    assert f"/chat/sessions/{sid}" in resp.text


# --------------------------------------------------------------------------- analytics interface link

def test_interface_has_analytics_link(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}")
    assert resp.status_code == 200
    assert "analytics" in resp.text.lower()
    assert f"/chat/sessions/{sid}/analytics" in resp.text


# --------------------------------------------------------------------------- CSV download

def test_csv_download_returns_correct_content_type(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    assert resp.status_code == 200
    assert "csv" in resp.headers.get("content-type", "").lower()


def test_csv_download_has_correct_headers(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    assert resp.status_code == 200
    first_line = resp.text.split("\n")[0]
    assert "turnIndex" in first_line
    assert "userMessage" in first_line
    assert "assembledResponse" in first_line
    assert "overallVerdict" in first_line
    assert "parameterName" in first_line
    assert "score" in first_line


def test_csv_download_has_correct_filename(client) -> None:
    sid = _seed_session("My Session")
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    cd = resp.headers.get("content-disposition", "")
    assert "my-session-results.csv" in cd


def test_csv_download_contains_turn_data(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="Test utterance", assembled="Test response")
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    assert resp.status_code == 200
    assert "Test utterance" in resp.text
    assert "Test response" in resp.text
    assert "pass" in resp.text


def test_csv_download_excludes_in_progress(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="Completed")
    _add_in_progress_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    assert resp.status_code == 200
    assert "In progress message" not in resp.text
    assert "Completed" in resp.text


def test_csv_download_empty_session(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    assert resp.status_code == 200
    # Only header row
    lines = [l for l in resp.text.strip().split("\n") if l.strip()]
    assert len(lines) == 1


def test_csv_download_403_for_missing_session(client) -> None:
    resp = client.get("/chat/sessions/no-such/download-results.csv")
    assert resp.status_code in (403, 404)


def test_csv_filename_sanitisation_special_chars(client) -> None:
    sid = _seed_session("Hello World! 2024")
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    cd = resp.headers.get("content-disposition", "")
    assert "hello-world-2024-results.csv" in cd


def test_csv_filename_fallback_for_empty_name(client) -> None:
    sid = _seed_session("!!! ---")
    resp = client.get(f"/chat/sessions/{sid}/download-results.csv")
    cd = resp.headers.get("content-disposition", "")
    assert "session-" in cd
    assert "-results.csv" in cd


# --------------------------------------------------------------------------- JSON download

def test_json_download_returns_correct_content_type(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.json")
    assert resp.status_code == 200
    assert "json" in resp.headers.get("content-type", "").lower()


def test_json_download_has_correct_filename(client) -> None:
    sid = _seed_session("Test Session")
    _add_completed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.json")
    cd = resp.headers.get("content-disposition", "")
    assert "test-session-results.json" in cd


def test_json_download_structure(client) -> None:
    sid = _seed_session()
    _add_completed_turn(
        sid,
        user_message="Hi",
        assembled="Hello",
        overall_verdict="pass",
        params=[{"parameter_name": "relevance", "score": 0.9, "reasoning": "r", "verdict": "pass"}],
    )
    resp = client.get(f"/chat/sessions/{sid}/download-results.json")
    assert resp.status_code == 200
    data = json_mod.loads(resp.content)
    assert isinstance(data, list)
    assert len(data) == 1
    row = data[0]
    assert row["turnIndex"] == 1
    assert row["userMessage"] == "Hi"
    assert row["assembledResponse"] == "Hello"
    assert row["overallVerdict"] == "pass"
    assert row["errorStatus"] is None
    assert isinstance(row["parameters"], list)
    param = row["parameters"][0]
    assert param["parameter_name"] == "relevance"
    assert param["score"] == 0.9


def test_json_download_failed_turn_structure(client) -> None:
    sid = _seed_session()
    _add_failed_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.json")
    data = json_mod.loads(resp.content)
    row = data[0]
    assert row["overallVerdict"] is None
    assert row["errorStatus"] == "failed"
    assert row["errorStage"] == "connector_error"
    assert row["parameters"] == []


def test_json_download_excludes_in_progress(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid)
    _add_in_progress_turn(sid)
    resp = client.get(f"/chat/sessions/{sid}/download-results.json")
    data = json_mod.loads(resp.content)
    assert len(data) == 1


def test_json_download_empty_session(client) -> None:
    sid = _seed_session()
    resp = client.get(f"/chat/sessions/{sid}/download-results.json")
    data = json_mod.loads(resp.content)
    assert data == []


def test_json_download_403_for_missing_session(client) -> None:
    resp = client.get("/chat/sessions/no-such/download-results.json")
    assert resp.status_code in (403, 404)


# --------------------------------------------------------------------------- filters

def test_analytics_filter_by_verdict(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="Pass turn", overall_verdict="pass")
    _add_completed_turn(sid, user_message="Fail turn", overall_verdict="fail",
                        params=[{"parameter_name": "relevance", "score": 0.1, "reasoning": "bad", "verdict": "fail"},
                                {"parameter_name": "tone", "score": 0.1, "reasoning": "bad", "verdict": "fail"}])
    resp = client.get(f"/chat/sessions/{sid}/analytics?verdict=fail")
    assert resp.status_code == 200
    assert "Fail turn" in resp.text
    assert "Pass turn" not in resp.text


def test_analytics_filter_by_search(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="Apple question")
    _add_completed_turn(sid, user_message="Banana question")
    resp = client.get(f"/chat/sessions/{sid}/analytics?q=apple")
    assert resp.status_code == 200
    assert "Apple question" in resp.text
    assert "Banana question" not in resp.text


def test_analytics_filter_error_only(client) -> None:
    sid = _seed_session()
    _add_completed_turn(sid, user_message="Good turn")
    _add_failed_turn(sid, user_message="Bad turn")
    resp = client.get(f"/chat/sessions/{sid}/analytics?error_only=1")
    assert resp.status_code == 200
    assert "Bad turn" in resp.text
    assert "Good turn" not in resp.text


# --------------------------------------------------------------------------- filename sanitisation unit tests

def test_sanitise_filename_basic():
    from harness.ui.chat_session.view import _sanitise_filename
    assert _sanitise_filename("My Session", "abc123") == "my-session"


def test_sanitise_filename_special_chars():
    from harness.ui.chat_session.view import _sanitise_filename
    assert _sanitise_filename("Hello World! 2024", "abc123") == "hello-world-2024"


def test_sanitise_filename_fallback():
    from harness.ui.chat_session.view import _sanitise_filename
    result = _sanitise_filename("!!! ---", "abcdefgh-rest")
    assert result == "session-abcdefgh"


def test_sanitise_filename_empty():
    from harness.ui.chat_session.view import _sanitise_filename
    result = _sanitise_filename("", "abcdefgh-xyz")
    assert result == "session-abcdefgh"
