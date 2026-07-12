"""Headless job submission service (020).

Validates incoming test-case payloads, creates a Job in the DB, stages
utterances, wires the SSE event bus, and enqueues execution. All validation
errors are raised as FastAPI HTTPExceptions before any DB write occurs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException, status

from harness.connector.registry import ConnectorRegistryReader
from harness.evaluator.registry import EvaluatorRegistryReader
from harness.orchestrator.engine import enqueue_job
from harness.persistence import get_session
from harness.persistence.enums import JobStatus, TERMINAL_STATUSES
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    JobRepository,
    UtteranceRepository,
)
from harness.ui.api.job_event_bus import create_bus, get_bus
from harness.ui.api.schemas import (
    FailedCase,
    HeadlessJobSubmission,
    HeadlessJobSubmissionResponse,
    HeadlessJobResult,
    JobSummary,
)

_MAX_CASES = 100
_MAX_IN_FLIGHT = 2


def _absolute_url(path: str) -> str:
    """Prepend HARNESS_PUBLIC_URL when set; otherwise return the path as-is."""
    import os
    base = os.environ.get("HARNESS_PUBLIC_URL", "").rstrip("/")
    return f"{base}{path}" if base else path


def submit_job(
    submission: HeadlessJobSubmission,
    user: dict,
    loop: asyncio.AbstractEventLoop,
) -> HeadlessJobSubmissionResponse:
    """Validate, create, enqueue a headless job and return the URL handles."""
    owner_id: str = user["oid"]
    cases = submission.test_cases

    # --- input validation (all before any DB write) ---
    if len(cases) > _MAX_CASES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "Submission exceeds the 100-case limit.",
                "submitted": len(cases),
                "limit": _MAX_CASES,
            },
        )

    seen_ids: set[str] = set()
    for tc in cases:
        if not tc.id or not tc.id.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Test case id must be non-empty.",
            )
        if tc.id in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Duplicate test case id: '{tc.id}'.",
            )
        seen_ids.add(tc.id)
        if not tc.input_message or not tc.input_message.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Test case '{tc.id}' has an empty input_message.",
            )

    # --- connector / evaluator validation + in-flight check ---
    with get_session() as session:
        connector_entry = ConnectorRegistryReader(session).get(submission.connector_id)
        if connector_entry is None or connector_entry.archived:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Connector '{submission.connector_id}' not found or inactive.",
            )
        if connector_entry.expects_per_row_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Selected connector requires per-row passwords, "
                    "which are not supported by the headless API in v1."
                ),
            )

        evaluator_entry = EvaluatorRegistryReader(session).get(submission.evaluator_id)
        if evaluator_entry is None or evaluator_entry.archived:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluator '{submission.evaluator_id}' not found or inactive.",
            )

        in_flight = JobRepository(session).count_headless_non_terminal_by_user(owner_id)
        if in_flight >= _MAX_IN_FLIGHT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "detail": (
                        f"{in_flight} headless jobs already in flight. "
                        "Wait for one to complete before resubmitting."
                    ),
                    "in_flight": in_flight,
                },
            )

    # --- create job + stage utterances ---
    with get_session() as session:
        job_repo = JobRepository(session)
        job = job_repo.create_draft(
            name=_job_name(submission),
            description=None,
            created_by=owner_id,
        )
        job_id = job.job_id

        # Set headless metadata
        job.submission_source = "api"
        job.source_system = submission.source_system
        job.product_name = submission.product_name
        job.feature_name = submission.feature_name

        # Snapshot connector
        connector_reg = ConnectorRegistrationRepository(session).get(submission.connector_id)
        job_repo.set_connector_snapshot(job_id, connector_reg)

        # Snapshot evaluator
        evaluator_reg = EvaluationAgentRegistrationRepository(session).get(submission.evaluator_id)
        job_repo.set_evaluator_snapshot(job_id, evaluator_reg)

        # Stage utterances
        utterance_rows = [
            {
                "utterance_text": tc.input_message,
                "test_id": tc.id,
                "row_index": idx,
                "extra_metadata": _extra_fields(tc),
            }
            for idx, tc in enumerate(cases)
        ]
        UtteranceRepository(session).bulk_create(job_id, utterance_rows)

        # Record total count + transition to queued
        job.total_utterance_count = len(cases)
        session.flush()
        job_repo.transition_to_queued(job_id)

    # --- wire event bus and enqueue ---
    bus = create_bus(job_id)

    def _started_hook(jid: str) -> None:
        b = get_bus(jid)
        if b:
            loop.call_soon_threadsafe(b.push, "job_started", {})

    def _progress_hook(jid: str, processed: int, failed: int) -> None:
        b = get_bus(jid)
        if b:
            loop.call_soon_threadsafe(
                b.push, "progress", {"cases_completed": processed, "cases_failed": failed}
            )

    def _terminal_hook(jid: str, final_status: str, summary: dict) -> None:
        b = get_bus(jid)
        if not b:
            return
        if final_status == "completed":
            payload: dict[str, Any] = {
                "results_url": _absolute_url(f"/jobs/{jid}/detail"),
                "summary": summary,
            }
            loop.call_soon_threadsafe(b.push, "job_complete", payload)
        else:
            error_msg = (
                "Job cancelled by user" if final_status == "cancelled"
                else "Execution error"
            )
            payload = {"error": error_msg, "summary": summary}
            loop.call_soon_threadsafe(b.push, "job_failed", payload)

    enqueue_job(
        job_id,
        progress_callback=_progress_hook,
        job_started_callback=_started_hook,
        job_terminal_callback=_terminal_hook,
    )

    return HeadlessJobSubmissionResponse(
        job_id=job_id,
        stream_url=f"/api/headless/jobs/{job_id}/stream",
        result_url=f"/api/headless/jobs/{job_id}/result",
    )


def get_job_result(job_id: str, owner_id: str) -> HeadlessJobResult:
    """Return the current result / partial state of a headless job."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        if job.created_by != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

        terminal_vals = {s.value for s in TERMINAL_STATUSES}
        is_terminal = job.status in terminal_vals
        is_completed = job.status == JobStatus.COMPLETED.value
        is_cancelled = job.status == JobStatus.CANCELLED.value
        is_failed = job.status == JobStatus.FAILED.value

        if is_terminal:
            summary = _compute_summary(session, job)
        else:
            summary = JobSummary(
                total=job.total_utterance_count or 0,
                passed=max(0, (job.processed_count or 0) - (job.failed_count or 0)),
                failed=job.failed_count or 0,
                top_failures=[],
            )

        if is_completed:
            result_status = "completed"
            results_url = f"/jobs/{job_id}/detail"
        elif is_failed:
            result_status = "failed"
            results_url = None
        elif is_cancelled:
            result_status = "cancelled"
            results_url = None
        else:
            result_status = "in_progress"
            results_url = None

        return HeadlessJobResult(
            job_id=job_id,
            status=result_status,
            results_url=results_url,
            summary=summary if is_terminal else summary,
        )


def cancel_job(job_id: str, owner_id: str, loop: asyncio.AbstractEventLoop) -> dict:
    """Cancel a non-terminal headless job (FR-015)."""
    terminal_vals = {s.value for s in TERMINAL_STATUSES}

    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
        if job.created_by != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
        if job.status in terminal_vals:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": f"Job is already in terminal state: {job.status}.",
                    "current_status": job.status,
                },
            )
        # Transition to cancelling — the engine thread will call _finish_cancel.
        # For API-initiated cancel we also force immediate cancelled transition
        # when the job is still queued (not yet picked up by engine).
        current_status = job.status
        repo = JobRepository(session)
        if current_status == JobStatus.QUEUED.value:
            # Job hasn't started executing yet — cancel directly.
            repo.transition_to_cancelling(job_id)
            repo.transition_to_cancelled(job_id)
        else:
            repo.transition_to_cancelling(job_id)

    # Push terminal event on any open stream
    bus = get_bus(job_id)
    if bus:
        loop.call_soon_threadsafe(
            bus.push, "job_failed", {"error": "Job cancelled by user", "summary": {}}
        )

    return {"job_id": job_id, "status": "cancelled"}


# ------------------------------------------------------------------ helpers


def _job_name(submission: HeadlessJobSubmission) -> str:
    parts = filter(None, [submission.source_system, submission.product_name, submission.feature_name])
    label = " / ".join(parts) or "Headless Job"
    return f"[API] {label}"


def _extra_fields(tc) -> dict | None:
    """Return all fields beyond id and input_message as extra_metadata."""
    extra = {k: v for k, v in tc.model_dump().items() if k not in ("id", "input_message")}
    return extra if extra else None


def _compute_summary(session, job) -> JobSummary:
    """Build a full summary including top_failures from evaluation results."""
    from sqlalchemy import select
    from harness.persistence.models import EvaluationResult, Utterance

    failed_rows = list(
        session.execute(
            select(Utterance.test_id, Utterance.utterance_text)
            .join(EvaluationResult, EvaluationResult.utterance_id == Utterance.utterance_id)
            .where(
                Utterance.job_id == job.job_id,
                EvaluationResult.error_status == "failed",
            )
            .order_by(Utterance.row_index.asc())
            .limit(5)
        ).all()
    )

    top_failures = [
        FailedCase(id=test_id, input_message=utterance_text)
        for test_id, utterance_text in failed_rows
    ]

    return JobSummary(
        total=job.total_utterance_count or 0,
        passed=max(0, (job.processed_count or 0) - (job.failed_count or 0)),
        failed=job.failed_count or 0,
        top_failures=top_failures,
    )
