"""Results export route (005). On-demand download; no server-side file is written."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from harness.auth.middleware import require_auth
from harness.export import build_export
from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository, UtteranceRepository

router = APIRouter()

_NO_ROWS_STATUSES = {JobStatus.DRAFT.value, JobStatus.QUEUED.value}


@router.get("/jobs/{job_id}/export")
def export_job(
    request: Request,
    job_id: str,
    fmt: str = Query("csv", alias="format"),
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        if job.status in _NO_ROWS_STATUSES or not utterances:
            raise HTTPException(status_code=400, detail="No rows to export yet.")
        filename, mimetype, body = build_export(job, utterances, fmt)
    return Response(
        content=body,
        media_type=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
