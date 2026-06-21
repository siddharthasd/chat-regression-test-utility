"""Dashboard & Job Listing routes (002). The harness root page + cleanup actions.

Read-only triage surface (drill-in to 004, Create-New-Job to 003) plus the
failed/cancelled cleanup affordances. Near-real-time row updates are served by
`/dashboard/jobs.json` and a thin inline poller in the template.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from harness.auth.middleware import require_auth
from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository
from harness.ui._context import ctx
from harness.ui._templates import templates
from harness.ui.dashboard import view

router = APIRouter()

_DELETABLE = {JobStatus.FAILED.value, JobStatus.CANCELLED.value, JobStatus.COMPLETED.value}


def _list_jobs(session, user: dict):
    repo = JobRepository(session)
    if user and user.get("role") == "admin":
        return repo.list_all()
    oid = user.get("oid") if user else None
    if oid:
        return repo.list_by_owner_id(oid)
    return repo.list_all()


@router.get("/")
def index(
    request: Request,
    status: list[str] = Query([]),
    connector: list[str] = Query([]),
    created_by: list[str] = Query([]),
    q: str = Query(""),
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    user: dict = Depends(require_auth),
):
    is_admin = user.get("role") == "admin" if user else True
    now = datetime.now(UTC)
    with get_session() as session:
        jobs = _list_jobs(session, user)
        all_rows = [view.row_view(j, now) for j in jobs]

    facets = view.distinct_facets(all_rows)
    rows = view.apply_filters(
        all_rows, statuses=status, connectors=connector, created_bys=created_by, q=q
    )
    rows = view.sort_rows(rows, sort, dir)
    terminal_clearable = sum(1 for r in all_rows if r["deletable"])
    total_clearable = sum(1 for r in all_rows if r["terminal"])

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "rows": rows,
            "total_jobs": len(all_rows),
            "facets": facets,
            "selected": {"status": status, "connector": connector, "created_by": created_by},
            "q": q,
            "sort": sort,
            "dir": dir,
            "terminal_clearable": terminal_clearable,
            "total_clearable": total_clearable,
            "is_admin": is_admin,
            **ctx(request),
        },
    )


@router.get("/dashboard/jobs.json")
def jobs_json(request: Request, user: dict = Depends(require_auth)):
    """Live state for the poller (FR-012/013)."""
    now = datetime.now(UTC)
    with get_session() as session:
        rows = [view.row_view(j, now) for j in _list_jobs(session, user)]
    return {
        "jobs": [
            {
                "job_id": r["job_id"],
                "status": r["status"],
                "status_label": r["status_label"],
                "badge_class": r["badge_class"],
                "processed": r["processed"],
                "total": r["total"],
                "failed": r["failed_count"],
                "terminal": r["terminal"],
            }
            for r in rows
        ]
    }


@router.post("/dashboard/jobs/{job_id}/delete")
def delete_job(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Delete a single failed/cancelled job (FR-010b), re-checking status at execute time."""
    is_admin = user.get("role") == "admin" if user else True
    with get_session() as session:
        repo = JobRepository(session)
        job = repo.get(job_id) if is_admin else (
            repo.get_owned(job_id, user.get("oid")) if user and user.get("oid") else None
        )
        if job is None:
            raise HTTPException(status_code=404)
        if job.status not in _DELETABLE:
            now = datetime.now(UTC)
            all_rows = [view.row_view(j, now) for j in _list_jobs(session, user)]
            return templates.TemplateResponse(
                request,
                "dashboard/index.html",
                {
                    "rows": view.sort_rows(all_rows, "created_at", "desc"),
                    "total_jobs": len(all_rows),
                    "facets": view.distinct_facets(all_rows),
                    "selected": {"status": [], "connector": [], "created_by": []},
                    "q": "",
                    "sort": "created_at",
                    "dir": "desc",
                    "terminal_clearable": sum(1 for r in all_rows if r["deletable"]),
                    "error": f"Job is '{job.status}' and cannot be deleted from the dashboard.",
                    "is_admin": is_admin,
                    **ctx(request),
                },
                status_code=409,
            )
        repo.delete(job_id)
    return RedirectResponse(request.url_for("index"), status_code=303)


@router.post("/dashboard/clear-terminal")
def clear_terminal(request: Request, user: dict = Depends(require_auth)):
    """Delete every failed, cancelled, and completed-with-errors job atomically (FR-010c)."""
    with get_session() as session:
        JobRepository(session).delete_all_clearable()
    return RedirectResponse(request.url_for("index"), status_code=303)


@router.post("/dashboard/clear-all", name="clear_all")
def clear_all(request: Request, user: dict = Depends(require_auth)):
    """Delete all terminal jobs — scoped to owner for users, global for admins."""
    is_admin = user.get("role") == "admin" if user else True
    oid = user.get("oid") if user else None
    with get_session() as session:
        repo = JobRepository(session)
        if is_admin or not oid:
            repo.delete_all_terminal()
        else:
            repo.delete_all_terminal_by_owner(oid)
    return RedirectResponse(request.url_for("index"), status_code=303)
