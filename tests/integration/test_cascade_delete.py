"""Cascade-delete + status-gate integration tests (US3).

Covers SC-006 (atomic cascade), SC-007 (non-deletable statuses refused), and
FR-012 (bulk clear-failed-and-cancelled).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from harness.persistence.enums import JobStatus
from harness.persistence.exceptions import JobNotDeletableError
from harness.persistence.models import EvaluationResult, Utterance
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)


def _job_in_status(db_session, status: JobStatus):
    """Build a job and drive it to the requested lifecycle status."""
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    conn = ConnectorRegistrationRepository(db_session).create(
        {"display_name": "C", "endpoint_url": "https://c", "auth_descriptor": {"mode": "none"}}
    )
    agent = EvaluationAgentRegistrationRepository(db_session).create(
        {
            "display_name": "E",
            "description": "d",
            "endpoint_url": "https://e",
            "auth_descriptor": {"mode": "none"},
        }
    )
    jobs.set_connector_snapshot(job.job_id, conn)
    jobs.set_evaluator_snapshot(job.job_id, agent)
    utt = UtteranceRepository(db_session).bulk_create(
        job.job_id, [{"utterance_text": "x", "test_id": "t1", "row_index": 1}]
    )[0]

    if status == JobStatus.DRAFT:
        return job
    jobs.transition_to_queued(job.job_id)
    if status == JobStatus.QUEUED:
        return job
    jobs.transition_to_running(job.job_id)
    if status == JobStatus.RUNNING:
        return job
    if status == JobStatus.COMPLETED:
        EvaluationResultRepository(db_session).create(
            {
                "utterance_id": utt.utterance_id,
                "test_id": "t1",
                "evaluation_timestamp": datetime.now(UTC),
            }
        )
        jobs.transition_to_completed(job.job_id)
        return job
    if status == JobStatus.FAILED:
        jobs.transition_to_failed(job.job_id, "boom")
        return job
    if status in (JobStatus.CANCELLING, JobStatus.CANCELLED):
        jobs.transition_to_cancelling(job.job_id)
        if status == JobStatus.CANCELLING:
            return job
        jobs.transition_to_cancelled(job.job_id)
        return job
    raise AssertionError(status)


def test_cascade_atomic_for_failed(db_session) -> None:
    jobs = JobRepository(db_session)
    job = _job_in_status(db_session, JobStatus.FAILED)
    assert UtteranceRepository(db_session).count_by_job(job.job_id) == 1
    jobs.delete(job.job_id)
    assert jobs.get(job.job_id) is None
    assert db_session.query(Utterance).filter_by(job_id=job.job_id).count() == 0
    assert db_session.query(EvaluationResult).count() == 0


@pytest.mark.parametrize("status", [JobStatus.DRAFT, JobStatus.FAILED, JobStatus.CANCELLED])
def test_status_gate_deletable(db_session, status) -> None:
    jobs = JobRepository(db_session)
    job = _job_in_status(db_session, status)
    jobs.delete(job.job_id)
    assert jobs.get(job.job_id) is None


@pytest.mark.parametrize(
    "status", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING, JobStatus.COMPLETED]
)
def test_status_gate_non_deletable(db_session, status) -> None:
    jobs = JobRepository(db_session)
    job = _job_in_status(db_session, status)
    with pytest.raises(JobNotDeletableError):
        jobs.delete(job.job_id)
    assert jobs.get(job.job_id) is not None


def test_bulk_delete_failed_and_cancelled(db_session) -> None:
    jobs = JobRepository(db_session)
    failed = _job_in_status(db_session, JobStatus.FAILED)
    cancelled = _job_in_status(db_session, JobStatus.CANCELLED)
    completed = _job_in_status(db_session, JobStatus.COMPLETED)

    deleted = jobs.delete_all_failed_and_cancelled()
    assert deleted == 2
    assert jobs.get(failed.job_id) is None
    assert jobs.get(cancelled.job_id) is None
    assert jobs.get(completed.job_id) is not None  # untouched
