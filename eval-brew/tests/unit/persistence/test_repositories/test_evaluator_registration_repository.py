"""EvaluationAgentRegistrationRepository tests (US1)."""

from __future__ import annotations

import pytest

from harness.persistence.repositories import EvaluationAgentRegistrationRepository


def _data(**over):
    base = {
        "display_name": "My Evaluator",
        "description": "Scores responses",
        "endpoint_url": "https://eval.test",
        "auth_descriptor": {"mode": "basic", "username": "u", "password": "PW-SECRET-7"},
        "declared_scoring_dimensions": ["accuracy", "tone"],
    }
    base.update(over)
    return base


def test_create_defaults_and_dimensions(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(_data())
    assert reg.timeout_seconds == 60
    assert reg.declared_scoring_dimensions == ["accuracy", "tone"]


def test_password_subfield_encrypted_and_username_plaintext(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(_data())
    assert reg.auth_descriptor["password"] != "PW-SECRET-7"
    assert reg.auth_descriptor["username"] == "u"
    assert repo.get_auth_descriptor_decrypted(reg.evaluation_agent_id)["password"] == "PW-SECRET-7"


def test_get_declared_dimensions(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(_data())
    assert repo.get_declared_dimensions(reg.evaluation_agent_id) == ["accuracy", "tone"]


def test_empty_dimensions_allowed(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(_data(declared_scoring_dimensions=[]))
    assert repo.get_declared_dimensions(reg.evaluation_agent_id) == []


def test_get_active_excludes_archived(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    a = repo.create(_data(display_name="A"))
    b = repo.create(_data(display_name="B"))
    repo.archive(b.evaluation_agent_id)
    active_ids = {r.evaluation_agent_id for r in repo.get_active()}
    assert a.evaluation_agent_id in active_ids
    assert b.evaluation_agent_id not in active_ids


def test_update_fields_and_reencrypt(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(_data())
    repo.update(
        reg.evaluation_agent_id,
        {
            "description": "updated",
            "declared_scoring_dimensions": ["x"],
            "auth_descriptor": {"mode": "bearer", "credential": "NEW-TOK"},
        },
    )
    assert repo.get(reg.evaluation_agent_id).description == "updated"
    assert repo.get_declared_dimensions(reg.evaluation_agent_id) == ["x"]
    assert repo.get_auth_descriptor_decrypted(reg.evaluation_agent_id)["credential"] == "NEW-TOK"


def test_archive_restore_and_hard_delete(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(_data())
    repo.archive(reg.evaluation_agent_id)
    assert repo.get(reg.evaluation_agent_id).archived is True
    repo.restore(reg.evaluation_agent_id)
    assert repo.get(reg.evaluation_agent_id).archived is False
    repo.hard_delete(reg.evaluation_agent_id)
    assert repo.get(reg.evaluation_agent_id) is None


def test_missing_evaluator_raises(db_session) -> None:
    repo = EvaluationAgentRegistrationRepository(db_session)
    with pytest.raises(ValueError):
        repo.get_declared_dimensions("nope")
