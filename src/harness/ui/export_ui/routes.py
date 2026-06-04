"""Results export route (005). On-demand download; no server-side file is written."""

from __future__ import annotations

from flask import Blueprint, Response, abort, request

from harness.export import build_export
from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository, UtteranceRepository

bp = Blueprint("export", __name__)

_NO_ROWS_STATUSES = {JobStatus.DRAFT.value, JobStatus.QUEUED.value}


@bp.route("/jobs/<job_id>/export", methods=["GET"])
def export(job_id: str):
    fmt = request.args.get("format", "csv")
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            abort(404)  # deleted between click and stream (FR-014)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        if job.status in _NO_ROWS_STATUSES or not utterances:
            abort(400, description="No rows to export yet.")
        filename, mimetype, body = build_export(job, utterances, fmt)
    return Response(
        body,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
