"""Job execution engine: run_job / enqueue_job / reconcile_orphans (012).

`run_job` is the synchronous, testable core — it drives one Job through its
per-row loop and lifecycle transitions. `enqueue_job` runs it on a daemon thread
behind a concurrency semaphore (async start, FR-001/022). `reconcile_orphans`
fails any Job left `running`/`cancelling` by a prior process (FR-002).

The engine assigns no verdicts and maps no error stages itself — `process_row`
(via 007/008) does that. The engine owns only the loop, the per-row transaction,
cancellation at row boundaries, the empty-store pre-row gate, and terminal
transitions.
"""

from __future__ import annotations

import logging
import threading

from harness import password_store
from harness.orchestrator.pipeline import process_row
from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.models import Utterance
from harness.persistence.repositories import (
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)

logger = logging.getLogger("harness.orchestrator")

#: Plan-level cap on concurrently-running jobs (parent: tuning concern). Excess
#: enqueue_job callers block on the semaphore until a slot frees.
MAX_CONCURRENT_JOBS = 4
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)


def run_job(job_id: str) -> None:
    """Execute one Job synchronously: queued/running → completed | cancelled | failed."""
    try:
        with get_session() as session:
            JobRepository(session).transition_to_running(job_id)

        # Snapshot the row list + the per-row-password flag up front.
        with get_session() as session:
            job = JobRepository(session).get(job_id)
            expects_password = job.connector_expects_per_row_password
            rows = UtteranceRepository(session).get_by_job_ordered(job_id)
            utterance_ids = [u.utterance_id for u in rows]

        # US6 pre-row gate: a per-row-password job with an empty store cannot run
        # (the store didn't survive a restart between upload and start) (FR-017).
        if expects_password and not password_store.job_has_entries(job_id):
            with get_session() as session:
                JobRepository(session).transition_to_failed(
                    job_id,
                    "credentials no longer in memory — re-upload CSV via a new job",
                )
            password_store.clear_job(job_id)
            return

        for utterance_id in utterance_ids:
            if _is_cancelling(job_id):
                _finish_cancel(job_id)
                return
            _process_one(job_id, utterance_id)

        # A cancel may have arrived during the final row.
        if _is_cancelling(job_id):
            _finish_cancel(job_id)
            return

        with get_session() as session:
            JobRepository(session).transition_to_completed(job_id)
        password_store.clear_job(job_id)
    except Exception as exc:  # noqa: BLE001 — engine-level failure → job failed (FR-016)
        logger.exception("orchestrator: job %s failed", job_id)
        _fail_safely(job_id, f"orchestrator error: {exc!r}")


def _process_one(job_id: str, utterance_id: str) -> None:
    """Run a row's pipeline, then persist its result + counters atomically (FR-014).

    The two HTTP calls run OUTSIDE any DB transaction so a slow connector/evaluator
    never holds the SQLite write lock — that keeps cancellation and concurrent jobs
    responsive. The result + counter writes then commit together in one short
    transaction.
    """
    # Read the (detached) Job + Utterance; expire_on_commit=False keeps attributes
    # loaded after the session closes, so process_row can read them lock-free.
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        utterance = session.get(Utterance, utterance_id)
        session.expunge_all()

    data = process_row(job, utterance)

    with get_session() as session:
        EvaluationResultRepository(session).create(data)
        jobs = JobRepository(session)
        jobs.increment_processed_count(job_id)
        if data.get("error_status") == "failed":
            jobs.increment_failed_count(job_id)


def _is_cancelling(job_id: str) -> bool:
    with get_session() as session:
        return JobRepository(session).get(job_id).status == JobStatus.CANCELLING


def _finish_cancel(job_id: str) -> None:
    """cancelling → cancelled (009 stubs the remaining rows) + clear the store (FR-020)."""
    with get_session() as session:
        JobRepository(session).transition_to_cancelled(job_id)
    password_store.clear_job(job_id)


def _fail_safely(job_id: str, details: str) -> None:
    try:
        with get_session() as session:
            JobRepository(session).transition_to_failed(job_id, details)
    except Exception:  # noqa: BLE001 — best-effort; job may already be terminal
        logger.exception("orchestrator: could not mark job %s failed", job_id)
    finally:
        password_store.clear_job(job_id)


def enqueue_job(job_id: str) -> None:
    """Start a Job asynchronously on a daemon worker thread (FR-001/022).

    Acquires a concurrency slot (released when the worker finishes) and returns
    immediately; the caller (wizard/UI request) never blocks on job completion.
    """

    def _worker() -> None:
        _slots.acquire()
        try:
            run_job(job_id)
        finally:
            _slots.release()

    threading.Thread(target=_worker, name=f"job-{job_id}", daemon=True).start()


def reconcile_orphans() -> None:
    """Fail any Job left `running`/`cancelling` by a crashed prior process (FR-002).

    Idempotent; runs at startup before any other module touches persistent state.
    """
    with get_session() as session:
        jobs = JobRepository(session)
        orphans = [
            (j.job_id, j.status)
            for j in jobs.get_by_status(JobStatus.RUNNING.value)
            + jobs.get_by_status(JobStatus.CANCELLING.value)
        ]
        for job_id, status in orphans:
            jobs.transition_to_failed(
                job_id, f"harness restarted while job was {status}"
            )
