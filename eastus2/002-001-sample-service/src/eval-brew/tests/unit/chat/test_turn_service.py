"""TurnService unit tests (017 US3) — turn lifecycle and conflict rejection."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from harness.chat.session_service import ChatSessionService
from harness.chat.turn_service import TurnService
from harness.persistence.repositories.connector_registration import (
    ConnectorRegistrationRepository,
)
from harness.persistence.repositories.evaluator_registration import (
    EvaluationAgentRegistrationRepository,
)


def _make_session(db_session) -> str:
    ConnectorRegistrationRepository(db_session).create({
        "display_name": "C", "endpoint_url": "https://c.test",
        "auth_descriptor": {"mode": "none"}, "timeout_seconds": 30,
        "expects_per_row_password": False, "supports_sse": True,
    })
    EvaluationAgentRegistrationRepository(db_session).create({
        "display_name": "E", "description": "e", "endpoint_url": "https://e.test",
        "auth_descriptor": {"mode": "none"}, "timeout_seconds": 60,
        "declared_scoring_dimensions": [], "supports_sse": True,
    })
    from harness.persistence.repositories.connector_registration import ConnectorRegistrationRepository as CR
    from harness.persistence.repositories.evaluator_registration import EvaluationAgentRegistrationRepository as ER
    from sqlalchemy import select
    from harness.persistence.models.connector_registration import ConnectorRegistration
    from harness.persistence.models.evaluator_registration import EvaluationAgentRegistration
    cid = db_session.scalar(select(ConnectorRegistration.connector_id))
    eid = db_session.scalar(select(EvaluationAgentRegistration.evaluation_agent_id))
    svc = ChatSessionService(db_session)
    sess = svc.create_session("S", cid, "tid", "pw", eid, "oid-1")
    return sess.chat_session_id


# --------------------------------------------------------------------------- creation
def test_create_turn_in_progress_status(db_session) -> None:
    session_id = _make_session(db_session)
    svc = TurnService(db_session)

    turn = svc.create_turn(session_id, "hello")

    assert turn.status == "in_progress"
    assert turn.user_message == "hello"
    assert turn.session_id == session_id


def test_create_turn_raises_409_if_in_progress(db_session) -> None:
    session_id = _make_session(db_session)
    svc = TurnService(db_session)

    svc.create_turn(session_id, "first message")

    with pytest.raises(HTTPException) as exc_info:
        svc.create_turn(session_id, "second message")

    assert exc_info.value.status_code == 409
    assert "in progress" in exc_info.value.detail.lower()


def test_get_turn_returns_correct_turn(db_session) -> None:
    session_id = _make_session(db_session)
    svc = TurnService(db_session)

    turn = svc.create_turn(session_id, "my message")
    fetched = svc.get_turn(turn.turn_id, session_id)

    assert fetched is not None
    assert fetched.turn_id == turn.turn_id
    assert fetched.user_message == "my message"


def test_get_turn_wrong_session_returns_none(db_session) -> None:
    session_id = _make_session(db_session)
    svc = TurnService(db_session)

    turn = svc.create_turn(session_id, "msg")
    result = svc.get_turn(turn.turn_id, "wrong-session-id")

    assert result is None


def test_create_turn_strips_whitespace(db_session) -> None:
    session_id = _make_session(db_session)
    svc = TurnService(db_session)

    turn = svc.create_turn(session_id, "  trimmed  ")

    assert turn.user_message == "trimmed"
