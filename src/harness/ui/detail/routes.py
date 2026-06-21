"""Job Detail & Traceability View routes (004). The dashboard's row-click target.

Read-and-act surface for one job: metadata panel + results table + full-trace expand,
reconstructed-CSV download, live polling, and the canonical Cancel/Delete actions.
The Job snapshot is the source of truth — registries are never consulted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response

from harness.auth.middleware import require_auth
from harness.persistence import get_session
from harness.persistence.enums import DELETABLE_STATUSES, JobStatus
from harness.persistence.exceptions import InvalidTransitionError
from harness.persistence.repositories import JobRepository, UtteranceRepository
from harness.ui._context import ctx
from harness.ui._templates import templates
from harness.ui.detail import view

router = APIRouter()

_CANCELLABLE = {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
_DELETABLE = {s.value for s in DELETABLE_STATUSES}
_ALWAYS_DELETABLE = {JobStatus.DRAFT.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}


def _can_delete(job) -> bool:
    """Show Delete button for draft, failed, cancelled, or completed-with-errors."""
    return job.status in _ALWAYS_DELETABLE or (
        job.status == JobStatus.COMPLETED.value and (job.failed_count or 0) > 0
    )


def _can_delete_from_meta(meta: dict) -> bool:
    return meta["status"] in _ALWAYS_DELETABLE or (
        meta["status"] == JobStatus.COMPLETED.value and (meta.get("failed_count") or 0) > 0
    )


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "on", "yes"}


@router.get("/jobs/{job_id}/detail")
def job_detail(
    request: Request,
    job_id: str,
    verdict: list[str] = Query([]),
    error_only: str = Query(""),
    test_id: list[str] = Query([]),
    q: str = Query(""),
    sort: str = Query("row_index"),
    dir: str = Query("asc"),
    user: dict = Depends(require_auth),
):
    verdicts = verdict
    error_only_bool = _truthy(error_only)
    test_ids = test_id
    direction = dir

    now = datetime.now(UTC)
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        meta = view.metadata_view(job, now)
        dims = meta["declared_dimensions"]
        all_rows = [
            view.row_view(u, dims) for u in UtteranceRepository(session).get_by_job_ordered(job_id)
        ]
        can_export = bool(all_rows) and job.status not in {
            JobStatus.DRAFT.value, JobStatus.QUEUED.value
        }
        job_status = job.status
        can_cancel = job_status in _CANCELLABLE
        can_delete = _can_delete(job)

    test_id_options = view.distinct_test_ids(all_rows)
    rows = view.apply_filters(
        all_rows, verdicts=verdicts, error_only=error_only_bool, test_ids=test_ids, q=q
    )
    rows = view.sort_rows(rows, sort, direction)
    filtered = bool(verdicts or error_only_bool or test_ids or q)

    return templates.TemplateResponse(
        request,
        "detail/index.html",
        {
            "meta": meta,
            "rows": rows,
            "declared_dimensions": dims,
            "test_id_options": test_id_options,
            "selected": {"verdict": verdicts, "test_id": test_ids},
            "error_only": error_only_bool,
            "q": q,
            "sort": sort,
            "dir": direction,
            "visible_n": len(rows),
            "visible_m": len(all_rows),
            "filtered": filtered,
            "can_cancel": can_cancel,
            "can_delete": can_delete,
            "can_export": can_export,
            "error": None,
            **ctx(request),
        },
    )


@router.get("/jobs/{job_id}/detail.json")
def detail_json(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Live state for the poller (FR-015/016); 404 when the job is gone (FR-020)."""
    now = datetime.now(UTC)
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        meta = view.metadata_view(job, now)
        row_count = UtteranceRepository(session).count_by_job(job_id)
    return {
        "status": meta["status"],
        "status_label": meta["status_label"],
        "badge_class": meta["badge_class"],
        "total": meta["total_utterance_count"],
        "processed": meta["processed_count"],
        "failed": meta["failed_count"],
        "row_count": row_count,
        "terminal": meta["terminal"],
    }


@router.get("/jobs/{job_id}/download.csv")
def download_csv(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = view.reconstruct_csv(job, utterances)
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/jobs/{job_id}/cancel")
def cancel(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        repo = JobRepository(session)
        if repo.get(job_id) is None:
            raise HTTPException(status_code=404)
        try:
            repo.transition_to_cancelling(job_id)
        except InvalidTransitionError:
            return _rerender_error(
                request, job_id, "Job is no longer cancellable (already terminal).", 409
            )
    return RedirectResponse(request.url_for("job_detail", job_id=job_id), status_code=303)


@router.post("/jobs/{job_id}/delete")
def job_delete(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        repo = JobRepository(session)
        job = repo.get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        if not _can_delete(job):
            return _rerender_error(
                request,
                job_id,
                f"Job is '{job.status}' and cannot be deleted from this view.",
                409,
            )
        repo.delete(job_id)
    return RedirectResponse(request.url_for("index"), status_code=303)


def _rerender_error(request: Request, job_id: str, message: str, status_code: int):
    now = datetime.now(UTC)
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        meta = view.metadata_view(job, now)
        dims = meta["declared_dimensions"]
        rows = [
            view.row_view(u, dims)
            for u in UtteranceRepository(session).get_by_job_ordered(job_id)
        ]
    return templates.TemplateResponse(
        request,
        "detail/index.html",
        {
            "meta": meta,
            "rows": rows,
            "declared_dimensions": dims,
            "test_id_options": view.distinct_test_ids(rows),
            "selected": {"verdict": [], "test_id": []},
            "error_only": False,
            "q": "",
            "sort": "row_index",
            "dir": "asc",
            "visible_n": len(rows),
            "visible_m": len(rows),
            "filtered": False,
            "can_cancel": meta["status"] in _CANCELLABLE,
            "can_delete": _can_delete_from_meta(meta),
            "can_export": bool(rows)
            and meta["status"] not in {JobStatus.DRAFT.value, JobStatus.QUEUED.value},
            "error": message,
            **ctx(request),
        },
        status_code=status_code,
    )
