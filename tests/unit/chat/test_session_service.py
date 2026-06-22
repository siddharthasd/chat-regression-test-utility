"""ChatSessionService unit tests (017 US1) — credential encryption and snapshots."""

from __future__ import annotations

import pytest

from harness.chat.session_service import ChatSessionService
from harness.persistence.encryption import decrypt_credential
from harness.persistence.repositories.connector_registration import (
    ConnectorRegistrationRepository,
)
from harness.persistence.repositories.evaluator_registration import (
    EvaluationAgentRegistrationRepository,
)


def _seed_connector(session, *, sse=True, name="SSEConn") -> str:
    reg = ConnectorRegistrationRepository(session).create({
        "display_name": name,
        "endpoint_url": "https://conn.test/api",
        "auth_descriptor": {"mode": "none"},
        "timeout_seconds": 30,
        "expects_per_row_password": False,
        "supports_sse": sse,
    })
    return reg.connector_id


def _seed_evaluator(session, *, sse=True, name="SSEEval") -> str:
    reg = EvaluationAgentRegistrationRepository(session).create({
        "display_name": name,
        "description": "scores",
        "endpoint_url": "https://eval.test/api",
        "auth_descriptor": {"mode": "none"},
        "timeout_seconds": 60,
        "declared_scoring_dimensions": ["relevance"],
        "supports_sse": sse,
    })
    return reg.evaluation_agent_id


# --------------------------------------------------------------------------- creation
def test_create_session_encrypts_credentials(db_session) -> None:
    cid = _seed_connector(db_session)
    eid = _seed_evaluator(db_session)
    svc = ChatSessionService(db_session)

    session = svc.create_session(
        name="My Session",
        connector_id=cid,
        test_id="user@test",
        password="s3cret",
        evaluator_id=eid,
        owner_oid="oid-alice",
    )

    # Credentials are stored as ciphertext — not plaintext
    assert session.test_id_enc != "user@test"
    assert session.test_password_enc != "s3cret"

    # Decrypted values round-trip correctly
    assert decrypt_credential(session.test_id_enc) == "user@test"
    assert decrypt_credential(session.test_password_enc) == "s3cret"


def test_create_session_snapshots_connector_fields(db_session) -> None:
    cid = _seed_connector(db_session, name="MyConnector")
    eid = _seed_evaluator(db_session)
    svc = ChatSessionService(db_session)

    session = svc.create_session("S", cid, "t", "p", eid, "oid-1")

    assert session.connector_id == cid
    assert session.connector_name == "MyConnector"
    assert session.connector_endpoint_url == "https://conn.test/api"
    assert session.connector_timeout_seconds == 30


def test_create_session_snapshots_evaluator_fields(db_session) -> None:
    cid = _seed_connector(db_session)
    eid = _seed_evaluator(db_session, name="MyEval")
    svc = ChatSessionService(db_session)

    session = svc.create_session("S", cid, "t", "p", eid, "oid-1")

    assert session.evaluator_id == eid
    assert session.evaluator_name == "MyEval"
    assert session.evaluator_endpoint_url == "https://eval.test/api"
    assert session.evaluator_timeout_seconds == 60


def test_create_session_records_owner_oid(db_session) -> None:
    cid = _seed_connector(db_session)
    eid = _seed_evaluator(db_session)
    svc = ChatSessionService(db_session)

    session = svc.create_session("S", cid, "t", "p", eid, "oid-owner-xyz")

    assert session.owner_oid == "oid-owner-xyz"


# --------------------------------------------------------------------------- guards
def test_create_session_rejects_non_sse_connector(db_session) -> None:
    cid = _seed_connector(db_session, sse=False)
    eid = _seed_evaluator(db_session)
    svc = ChatSessionService(db_session)

    with pytest.raises(ValueError, match="does not support SSE"):
        svc.create_session("S", cid, "t", "p", eid, "oid-1")


def test_create_session_rejects_non_sse_evaluator(db_session) -> None:
    cid = _seed_connector(db_session)
    eid = _seed_evaluator(db_session, sse=False)
    svc = ChatSessionService(db_session)

    with pytest.raises(ValueError, match="does not support SSE"):
        svc.create_session("S", cid, "t", "p", eid, "oid-1")


def test_create_session_rejects_unknown_connector(db_session) -> None:
    eid = _seed_evaluator(db_session)
    svc = ChatSessionService(db_session)

    with pytest.raises(ValueError, match="not found or archived"):
        svc.create_session("S", "no-such-id", "t", "p", eid, "oid-1")


# --------------------------------------------------------------------------- decrypt helpers
def test_decrypt_test_id_and_password(db_session) -> None:
    cid = _seed_connector(db_session)
    eid = _seed_evaluator(db_session)
    svc = ChatSessionService(db_session)

    session = svc.create_session("S", cid, "my-test-id", "my-pw", eid, "oid-1")

    assert svc.decrypt_test_id(session) == "my-test-id"
    assert svc.decrypt_password(session) == "my-pw"
