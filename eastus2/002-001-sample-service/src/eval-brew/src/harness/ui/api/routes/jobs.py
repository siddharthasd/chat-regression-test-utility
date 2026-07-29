"""Headless job endpoints (020): submit, stream, result, cancel."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from harness.ui.api.auth import require_api_auth
from harness.ui.api.job_event_bus import get_bus
from harness.ui.api.schemas import HeadlessJobResult, HeadlessJobSubmission, HeadlessJobSubmissionResponse
from harness.ui.api.service import cancel_job, get_job_result, submit_job

router = APIRouter()


@router.post("/jobs", response_model=HeadlessJobSubmissionResponse, status_code=201)
async def post_job(
    submission: HeadlessJobSubmission,
    user: dict = Depends(require_api_auth),
) -> HeadlessJobSubmissionResponse:
    """Submit test cases as a headless job (FR-003)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: submit_job(submission, user, loop))


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: str,
    user: dict = Depends(require_api_auth),
) -> StreamingResponse:
    """SSE progress stream for a headless job (FR-005)."""
    from harness.persistence import get_session
    from harness.persistence.repositories import JobRepository

    # Ownership + existence check
    owner_id = user["oid"]
    with get_session() as session:
        job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.created_by != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

    bus = get_bus(job_id)
    if bus is None:
        # Job is terminal and bus was already removed — emit from DB result
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stream not available (job may have completed before stream was opened).",
        )

    async def _event_generator() -> AsyncIterator[str]:
        async for event in bus.stream(cursor=0):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"

    return StreamingResponse(_event_generator(), media_type="text/event-stream")


@router.get("/jobs/{job_id}/result", response_model=HeadlessJobResult)
def result_job(
    job_id: str,
    user: dict = Depends(require_api_auth),
) -> HeadlessJobResult:
    """Re-fetch the current state or final result of a headless job (FR-006)."""
    return get_job_result(job_id, user["oid"])


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user: dict = Depends(require_api_auth),
) -> dict:
    """Cancel a headless job in any non-terminal state (FR-015)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: cancel_job(job_id, user["oid"], loop))
