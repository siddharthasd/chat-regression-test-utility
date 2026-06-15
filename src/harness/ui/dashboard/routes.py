"""Dashboard & Job Listing routes (002). The harness root page + cleanup actions.

Read-only triage surface (drill-in to 004, Create-New-Job to 003) plus the
failed/cancelled cleanup affordances. Near-real-time row updates are served by
`/dashboard/jobs.json` and a thin inline poller in the template.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository
from harness.ui.dashboard import view

bp = Blueprint("dashboard", __name__, template_folder="templates")

_DELETABLE = {JobStatus.FAILED.value, JobStatus.CANCELLED.value, JobStatus.COMPLETED.value}


@bp.route("/", methods=["GET"])
def index():
    statuses = request.args.getlist("status")
    connectors = request.args.getlist("connector")
    created_bys = request.args.getlist("created_by")
    q = request.args.get("q") or ""
    sort = request.args.get("sort") or "created_at"
    direction = request.args.get("dir") or "desc"

    now = datetime.now(UTC)
    with get_session() as session:
        jobs = JobRepository(session).list_all()
        all_rows = [view.row_view(j, now) for j in jobs]

    facets = view.distinct_facets(all_rows)
    rows = view.apply_filters(
        all_rows, statuses=statuses, connectors=connectors, created_bys=created_bys, q=q
    )
    rows = view.sort_rows(rows, sort, direction)
    terminal_clearable = sum(1 for r in all_rows if r["deletable"])

    return render_template(
        "dashboard/index.html",
        rows=rows,
        total_jobs=len(all_rows),
        facets=facets,
        selected={"status": statuses, "connector": connectors, "created_by": created_bys},
        q=q,
        sort=sort,
        dir=direction,
        terminal_clearable=terminal_clearable,
    )


@bp.route("/dashboard/jobs.json", methods=["GET"])
def jobs_json():
    """Live state for the poller (FR-012/013)."""
    now = datetime.now(UTC)
    with get_session() as session:
        rows = [view.row_view(j, now) for j in JobRepository(session).list_all()]
    return jsonify(
        jobs=[
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
    )


@bp.route("/dashboard/jobs/<job_id>/delete", methods=["POST"])
def delete_job(job_id: str):
    """Delete a single failed/cancelled job (FR-010b), re-checking status at execute time."""
    with get_session() as session:
        repo = JobRepository(session)
        job = repo.get(job_id)
        if job is None:
            abort(404)
        if job.status not in _DELETABLE:
            # Status changed between confirm and execute, or never deletable here.
            now = datetime.now(UTC)
            all_rows = [view.row_view(j, now) for j in repo.list_all()]
            return (
                render_template(
                    "dashboard/index.html",
                    rows=view.sort_rows(all_rows, "created_at", "desc"),
                    total_jobs=len(all_rows),
                    facets=view.distinct_facets(all_rows),
                    selected={"status": [], "connector": [], "created_by": []},
                    q="",
                    sort="created_at",
                    dir="desc",
                    terminal_clearable=sum(1 for r in all_rows if r["deletable"]),
                    error=f"Job is '{job.status}' and cannot be deleted from the dashboard.",
                ),
                409,
            )
        repo.delete(job_id)
    return redirect(url_for("dashboard.index"))


@bp.route("/dashboard/clear-terminal", methods=["POST"])
def clear_terminal():
    """Delete every failed, cancelled, and completed-with-errors job atomically (FR-010c)."""
    with get_session() as session:
        JobRepository(session).delete_all_clearable()
    return redirect(url_for("dashboard.index"))
