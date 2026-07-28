"""EvaluatorRegistryService tests (US1/2/3/4/6)."""

from __future__ import annotations

import pytest

from harness.evaluator import EvaluatorRegistryReader
from harness.evaluator_registry import EvaluatorRegistryService, RegistrationInUseError
from harness.persistence.repositories import JobRepository


def _payload(**over) -> dict:
    base = {
        "display_name": "E",
        "description": "d",
        "endpoint_url": "https://e.test",
        "auth_descriptor": {"mode": "bearer", "credential": "SEKRIT"},
        "timeout_seconds": 60,
        "declared_scoring_dimensions": ["relevance"],
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ US1
def test_create_encrypts_and_persists(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload())
    assert reg.evaluation_agent_id
    assert reg.auth_descriptor["credential"] != "SEKRIT"
    assert svc.get_auth_descriptor_decrypted(reg.evaluation_agent_id)["credential"] == "SEKRIT"


# ------------------------------------------------------------------ US3 dimensions
def test_dimensions_order_roundtrip(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload(declared_scoring_dimensions=["c", "a", "b"]))
    reader = EvaluatorRegistryReader(db_session)
    assert reader.get_declared_dimensions(reg.evaluation_agent_id) == ["c", "a", "b"]  # SC-011


def test_empty_dimensions_ok(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload(declared_scoring_dimensions=[]))
    assert svc.get(reg.evaluation_agent_id).declared_scoring_dimensions == []  # SC-012


# ------------------------------------------------------------------ US2
def test_update_preserves_ciphertext_without_replace(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload())
    before = reg.auth_descriptor["credential"]
    svc.update(
        reg.evaluation_agent_id,
        _payload(display_name="E2", auth_descriptor={"mode": "bearer", "credential": ""}),
        replace_credential=False,
    )
    after = svc.get(reg.evaluation_agent_id)
    assert after.display_name == "E2"
    assert after.auth_descriptor["credential"] == before


def test_mode_change_discards_old_credential(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload())
    svc.update(
        reg.evaluation_agent_id,
        _payload(auth_descriptor={"mode": "none"}),
        replace_credential=False,
    )
    desc = svc.get_auth_descriptor_decrypted(reg.evaluation_agent_id)
    assert desc == {"mode": "none"}  # bearer credential discarded


# ------------------------------------------------------------------ US4
def test_archive_and_restore(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload())
    svc.archive(reg.evaluation_agent_id)
    assert svc.get(reg.evaluation_agent_id).archived is True
    svc.restore(reg.evaluation_agent_id)
    assert svc.get(reg.evaluation_agent_id).archived is False


def test_list_filters_and_search(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    svc.create(_payload(display_name="Apple"))
    banana = svc.create(_payload(display_name="Banana"))
    svc.archive(banana.evaluation_agent_id)
    assert [r.display_name for r in svc.list_registrations(filter="active")] == ["Apple"]
    assert [r.display_name for r in svc.list_registrations(filter="archived")] == ["Banana"]
    assert [r.display_name for r in svc.list_registrations(filter="all", q="app")] == ["Apple"]


# ------------------------------------------------------------------ US6
def test_hard_delete_when_unreferenced(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload())
    svc.hard_delete(reg.evaluation_agent_id)
    assert svc.get(reg.evaluation_agent_id) is None


def test_hard_delete_blocked_when_referenced(db_session) -> None:
    svc = EvaluatorRegistryService(db_session)
    reg = svc.create(_payload())
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    jobs.set_evaluator_snapshot(job.job_id, reg)  # job.evaluation_agent_id == reg id
    with pytest.raises(RegistrationInUseError):
        svc.hard_delete(reg.evaluation_agent_id)
    assert svc.get(reg.evaluation_agent_id) is not None
