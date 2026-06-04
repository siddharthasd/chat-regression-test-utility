"""EvaluatorRegistryReader tests (US2, FR-008-013, SC-003/011)."""

from __future__ import annotations

from harness.evaluator import EvaluatorRegistryReader
from harness.persistence.repositories import EvaluationAgentRegistrationRepository


def _make(db_session, name: str, *, archived: bool = False, dims=("relevance",)):
    repo = EvaluationAgentRegistrationRepository(db_session)
    reg = repo.create(
        {
            "display_name": name,
            "description": f"{name} desc",
            "endpoint_url": "https://e.test",
            "auth_descriptor": {"mode": "none"},
            "declared_scoring_dimensions": list(dims),
        }
    )
    if archived:
        repo.archive(reg.evaluation_agent_id)
    return reg


def test_list_active_excludes_archived(db_session) -> None:
    active = _make(db_session, "A")
    gone = _make(db_session, "B", archived=True)
    ids = {e.evaluation_agent_id for e in EvaluatorRegistryReader(db_session).list_active()}
    assert active.evaluation_agent_id in ids
    assert gone.evaluation_agent_id not in ids


def test_list_entry_fields(db_session) -> None:
    reg = _make(db_session, "C", dims=("relevance", "groundedness"))
    entries = EvaluatorRegistryReader(db_session).list_active()
    entry = next(e for e in entries if e.evaluation_agent_id == reg.evaluation_agent_id)
    assert entry.display_name == "C"
    assert entry.description == "C desc"
    assert entry.declared_scoring_dimensions == ["relevance", "groundedness"]


def test_get_returns_full_record(db_session) -> None:
    reg = _make(db_session, "D")
    full = EvaluatorRegistryReader(db_session).get(reg.evaluation_agent_id)
    assert full.endpoint_url == "https://e.test"
    assert full.auth_descriptor["mode"] == "none"


def test_get_declared_dimensions(db_session) -> None:
    reg = _make(db_session, "E", dims=("x", "y", "z"))
    dims = EvaluatorRegistryReader(db_session).get_declared_dimensions(reg.evaluation_agent_id)
    assert dims == ["x", "y", "z"]  # SC-011


def test_identical_data_all_callers(db_session) -> None:
    reg = _make(db_session, "F")
    via_a = EvaluatorRegistryReader(db_session).get(reg.evaluation_agent_id).evaluation_agent_id
    via_b = EvaluatorRegistryReader(db_session).get(reg.evaluation_agent_id).evaluation_agent_id
    assert via_a == via_b == reg.evaluation_agent_id
