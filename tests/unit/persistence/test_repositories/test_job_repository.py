"""JobRepository tests: US1 (lifecycle), US2 (immutability + gate), US3 (cancel stubs)."""

from __future__ import annotations

import pytest

from harness.persistence.enums import JobStatus
from harness.persistence.exceptions import (
    InactiveRegistrationError,
    InvalidTransitionError,
    JobNotDeletableError,
    MissingSnapshotFieldError,
    SnapshotImmutableError,
)
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)


def _connector(db_session, **over):
    data = {
        "display_name": "Conn",
        "endpoint_url": "https://conn.test",
        "auth_descriptor": {"mode": "bearer", "credential": "TOK"},
    }
    data.update(over)
    return ConnectorRegistrationRepository(db_session).create(data)


def _evaluator(db_session, **over):
    data = {
        "display_name": "Eval",
        "description": "d",
        "endpoint_url": "https://eval.test",
        "auth_descriptor": {"mode": "none"},
    }
    data.update(over)
    return EvaluationAgentRegistrationRepository(db_session).create(data)


def _snapshotted_draft(db_session):
    """A draft Job with connector + evaluator snapshots and CSV metadata set."""
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "alice")
    jobs.set_connector_snapshot(job.job_id, _connector(db_session))
    jobs.set_evaluator_snapshot(job.job_id, _evaluator(db_session))
    jobs.set_csv_metadata(job.job_id, "in.csv", 0)
    return jobs, job


# ------------------------------------------------------------------ US1
def test_create_draft_stamps_version_and_defaults(db_session) -> None:
    job = JobRepository(db_session).create_draft("J", "desc", "alice")
    assert job.status == JobStatus.DRAFT
    assert job.created_by == "alice"
    assert job.harness_version == "0.1.0"
    assert job.processed_count == 0


def test_get_by_status(db_session) -> None:
    jobs = JobRepository(db_session)
    jobs.create_draft("A", None, "u")
    jobs.create_draft("B", None, "u")
    assert len(jobs.get_by_status(JobStatus.DRAFT.value)) == 2
    assert jobs.get_by_status(JobStatus.RUNNING.value) == []


def test_counter_increments(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    jobs.increment_processed_count(job.job_id)
    jobs.increment_processed_count(job.job_id)
    jobs.increment_failed_count(job.job_id)
    refreshed = jobs.get(job.job_id)
    assert refreshed.processed_count == 2
    assert refreshed.failed_count == 1


def test_happy_path_transitions(db_session) -> None:
    jobs, job = _snapshotted_draft(db_session)
    jobs.transition_to_queued(job.job_id)
    assert jobs.get(job.job_id).status == JobStatus.QUEUED
    assert jobs.get(job.job_id).started_at is not None
    jobs.transition_to_running(job.job_id)
    jobs.transition_to_completed(job.job_id)
    assert jobs.get(job.job_id).status == JobStatus.COMPLETED
    assert jobs.get(job.job_id).completed_at is not None


def test_invalid_transition_refused(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    with pytest.raises(InvalidTransitionError):
        jobs.transition_to_running(job.job_id)  # draft → running not allowed


# ------------------------------------------------------------------ US2 immutability
def test_immutability_snapshot_refused_past_draft(db_session) -> None:
    jobs, job = _snapshotted_draft(db_session)
    jobs.transition_to_queued(job.job_id)
    with pytest.raises(SnapshotImmutableError):
        jobs.set_csv_metadata(job.job_id, "other.csv", 5)
    with pytest.raises(SnapshotImmutableError):
        jobs.set_connector_snapshot(job.job_id, _connector(db_session))


def test_transition_gate_missing_connector(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    with pytest.raises(MissingSnapshotFieldError):
        jobs.transition_to_queued(job.job_id)


def test_transition_gate_archived_registration(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    conn = _connector(db_session)
    jobs.set_connector_snapshot(job.job_id, conn)
    jobs.set_evaluator_snapshot(job.job_id, _evaluator(db_session))
    ConnectorRegistrationRepository(db_session).archive(conn.connector_id)
    with pytest.raises(InactiveRegistrationError):
        jobs.transition_to_queued(job.job_id)


def test_snapshot_isolation_from_registry_edits(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    conn = _connector(db_session, endpoint_url="https://A")
    jobs.set_connector_snapshot(job.job_id, conn)
    # Mutate the registry after snapshot.
    ConnectorRegistrationRepository(db_session).update(
        conn.connector_id, {"endpoint_url": "https://B"}
    )
    assert jobs.get(job.job_id).connector_endpoint_url == "https://A"


# ------------------------------------------------------------------ US3 cancellation
def test_cancellation_stubs_created_atomically(db_session) -> None:
    jobs, job = _snapshotted_draft(db_session)
    UtteranceRepository(db_session).bulk_create(
        job.job_id,
        [
            {"utterance_text": "a", "test_id": "t1", "row_index": 1},
            {"utterance_text": "b", "test_id": "t2", "row_index": 2},
        ],
    )
    jobs.transition_to_queued(job.job_id)
    jobs.transition_to_running(job.job_id)
    jobs.transition_to_cancelling(job.job_id)
    jobs.transition_to_cancelled(job.job_id)

    results = EvaluationResultRepository(db_session).get_by_job(job.job_id)
    assert len(results) == 2  # one stub per utterance
    assert all(r.error_status == "cancelled" and r.error_stage is None for r in results)
    assert jobs.get(job.job_id).status == JobStatus.CANCELLED


def test_cancelled_requires_cancelling_state(db_session) -> None:
    jobs, job = _snapshotted_draft(db_session)
    jobs.transition_to_queued(job.job_id)
    with pytest.raises(InvalidTransitionError):
        jobs.transition_to_cancelled(job.job_id)


# ------------------------------------------------------------------ US3 delete gate
def test_delete_refused_for_completed(db_session) -> None:
    jobs, job = _snapshotted_draft(db_session)
    jobs.transition_to_queued(job.job_id)
    jobs.transition_to_running(job.job_id)
    jobs.transition_to_completed(job.job_id)
    with pytest.raises(JobNotDeletableError):
        jobs.delete(job.job_id)


def test_delete_allowed_for_draft(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    jobs.delete(job.job_id)
    assert jobs.get(job.job_id) is None
