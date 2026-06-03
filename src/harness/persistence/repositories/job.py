"""JobRepository (009, contract repository-api.md).

Owns the Job lifecycle: draft creation, config snapshots (immutable past draft —
FR-005), the draft→queued selection gate (FR-007a), status transitions, runtime
counters, status-gated cascade delete (FR-010/011), bulk delete (FR-012), and
atomic cancellation-stub creation (FR-003a). No ORM event listeners — all rules
are enforced here (research R7/R10).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from harness.persistence.enums import DELETABLE_STATUSES, JobStatus
from harness.persistence.exceptions import (
    InactiveRegistrationError,
    InvalidTransitionError,
    JobNotDeletableError,
    JobNotFoundError,
    MissingSnapshotFieldError,
    SnapshotImmutableError,
)
from harness.persistence.models import (
    ConnectorRegistration,
    EvaluationAgentRegistration,
    Job,
    Utterance,
)
from harness.persistence.repositories.evaluation_result import EvaluationResultRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _harness_version() -> str:
    try:
        return version("harness")
    except PackageNotFoundError:  # pragma: no cover - package always installed in tests
        return "0.0.0"


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------------- create/read
    def create_draft(self, name: str, description: str | None, created_by: str) -> Job:
        job = Job(
            job_id=str(uuid.uuid4()),
            job_name=name,
            description=description,
            status=JobStatus.DRAFT.value,
            created_by=created_by,
            created_at=_utcnow(),
            harness_version=_harness_version(),
            processed_count=0,
            failed_count=0,
        )
        self._session.add(job)
        self._session.flush()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._session.get(Job, job_id)

    def get_by_status(self, status: str) -> list[Job]:
        return list(self._session.scalars(select(Job).where(Job.status == status)))

    # -------------------------------------------------------------------- snapshots
    def set_connector_snapshot(
        self, job_id: str, registration: ConnectorRegistration
    ) -> None:
        job = self._require_draft(job_id, "connector_*")
        job.connector_id = registration.connector_id
        job.connector_name = registration.display_name
        job.connector_endpoint_url = registration.endpoint_url
        job.connector_auth_descriptor = registration.auth_descriptor  # verbatim ciphertext
        job.connector_timeout_seconds = registration.timeout_seconds
        job.connector_expects_per_row_password = registration.expects_per_row_password
        self._session.flush()

    def set_evaluator_snapshot(
        self, job_id: str, registration: EvaluationAgentRegistration
    ) -> None:
        job = self._require_draft(job_id, "evaluator_*")
        job.evaluation_agent_id = registration.evaluation_agent_id
        job.evaluation_agent_name = registration.display_name
        job.evaluator_endpoint_url = registration.endpoint_url
        job.evaluator_auth_descriptor = registration.auth_descriptor  # verbatim ciphertext
        job.evaluator_timeout_seconds = registration.timeout_seconds
        job.evaluator_declared_scoring_dimensions = registration.declared_scoring_dimensions
        self._session.flush()

    def set_csv_metadata(self, job_id: str, filename: str, row_count: int) -> None:
        job = self._require_draft(job_id, "source_csv_filename")
        job.source_csv_filename = filename
        job.total_utterance_count = row_count
        self._session.flush()

    # --------------------------------------------------------------------- counters
    def increment_processed_count(self, job_id: str) -> None:
        self._atomic_increment(job_id, "processed_count")

    def increment_failed_count(self, job_id: str) -> None:
        self._atomic_increment(job_id, "failed_count")

    def _atomic_increment(self, job_id: str, column: str) -> None:
        col = getattr(Job, column)
        result = self._session.execute(
            update(Job).where(Job.job_id == job_id).values({column: col + 1})
        )
        if result.rowcount == 0:
            raise JobNotFoundError(job_id)
        self._session.flush()

    # ------------------------------------------------------------------ transitions
    def transition_to_queued(self, job_id: str) -> None:
        job = self._require(job_id)
        if job.status != JobStatus.DRAFT:
            raise InvalidTransitionError(job_id, job.status, JobStatus.QUEUED.value)
        # FR-007a selection gate (defense-in-depth backstop for the wizard).
        if not job.connector_id:
            raise MissingSnapshotFieldError(job_id, "connectorId")
        if not job.evaluation_agent_id:
            raise MissingSnapshotFieldError(job_id, "evaluationAgentId")
        connector = self._session.get(ConnectorRegistration, job.connector_id)
        if connector is None or connector.archived:
            raise InactiveRegistrationError(job_id, "connector", job.connector_id)
        agent = self._session.get(EvaluationAgentRegistration, job.evaluation_agent_id)
        if agent is None or agent.archived:
            raise InactiveRegistrationError(
                job_id, "evaluationAgent", job.evaluation_agent_id
            )
        job.status = JobStatus.QUEUED.value
        job.started_at = _utcnow()
        self._session.flush()

    def transition_to_running(self, job_id: str) -> None:
        self._transition(job_id, {JobStatus.QUEUED}, JobStatus.RUNNING)

    def transition_to_completed(self, job_id: str) -> None:
        job = self._transition(job_id, {JobStatus.RUNNING}, JobStatus.COMPLETED)
        job.completed_at = _utcnow()
        self._session.flush()

    def transition_to_failed(self, job_id: str, error_details: str) -> None:
        job = self._transition(
            job_id,
            {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING},
            JobStatus.FAILED,
        )
        job.completed_at = _utcnow()
        job.error_details = error_details
        self._session.flush()

    def transition_to_cancelling(self, job_id: str) -> None:
        self._transition(job_id, {JobStatus.QUEUED, JobStatus.RUNNING}, JobStatus.CANCELLING)

    def transition_to_cancelled(self, job_id: str) -> None:
        """CANCELLING → CANCELLED, creating a stub for every un-processed row (FR-003a)."""
        job = self._require(job_id)
        if job.status != JobStatus.CANCELLING:
            raise InvalidTransitionError(job_id, job.status, JobStatus.CANCELLED.value)
        unprocessed = list(
            self._session.scalars(
                select(Utterance.utterance_id).where(
                    Utterance.job_id == job_id,
                    ~Utterance.evaluation_result.has(),
                )
            )
        )
        EvaluationResultRepository(self._session).bulk_create_stubs(
            unprocessed, job.evaluation_agent_id, _utcnow()
        )
        job.status = JobStatus.CANCELLED.value
        job.completed_at = _utcnow()
        self._session.flush()

    # ----------------------------------------------------------------------- delete
    def delete(self, job_id: str) -> None:
        job = self._require(job_id)
        if JobStatus(job.status) not in DELETABLE_STATUSES:
            raise JobNotDeletableError(job_id, job.status)
        self._session.delete(job)  # cascades Utterance + EvaluationResult
        self._session.flush()

    def delete_all_failed_and_cancelled(self) -> int:
        # Snapshot the qualifying id-set inside the transaction (FR-012 atomicity).
        job_ids = list(
            self._session.scalars(
                select(Job.job_id).where(
                    Job.status.in_(
                        [JobStatus.FAILED.value, JobStatus.CANCELLED.value]
                    )
                )
            )
        )
        for job_id in job_ids:
            self._session.delete(self._session.get(Job, job_id))
        self._session.flush()
        return len(job_ids)

    # ----------------------------------------------------------------------- helpers
    def _require(self, job_id: str) -> Job:
        job = self._session.get(Job, job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def _require_draft(self, job_id: str, field: str) -> Job:
        job = self._require(job_id)
        if job.status != JobStatus.DRAFT:
            raise SnapshotImmutableError(job_id, field)
        return job

    def _transition(
        self, job_id: str, allowed_from: set[JobStatus], to: JobStatus
    ) -> Job:
        job = self._require(job_id)
        if JobStatus(job.status) not in allowed_from:
            raise InvalidTransitionError(job_id, job.status, to.value)
        job.status = to.value
        self._session.flush()
        return job
