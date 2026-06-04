"""Job Detail & Traceability View routes (004). The dashboard's row-click target.

Read-and-act surface for one job: metadata panel + results table + full-trace expand,
reconstructed-CSV download, live polling, and the canonical Cancel/Delete actions.
The Job snapshot is the source of truth — registries are never consulted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from harness.persistence import get_session
from harness.persistence.enums import DELETABLE_STATUSES, JobStatus
from harness.persistence.exceptions import InvalidTransitionError
from harness.persistence.repositories import JobRepository, UtteranceRepository
from harness.ui.detail import view

bp = Blueprint("detail", __name__, template_folder="templates")

_CANCELLABLE = {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
_DELETABLE = {s.value for s in DELETABLE_STATUSES}


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "on", "yes"}


@bp.route("/jobs/<job_id>/detail", methods=["GET"])
def detail(job_id: str):
    verdicts = request.args.getlist("verdict")
    error_only = _truthy(request.args.get("error_only"))
    test_ids = request.args.getlist("test_id")
    q = request.args.get("q") or ""
    sort = request.args.get("sort") or "row_index"
    direction = request.args.get("dir") or "asc"

    now = datetime.now(UTC)
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            abort(404)
        meta = view.metadata_view(job, now)
        dims = meta["declared_dimensions"]
        all_rows = [
            view.row_view(u, dims) for u in UtteranceRepository(session).get_by_job_ordered(job_id)
        ]
        can_export = bool(all_rows) and job.status not in {
            JobStatus.DRAFT.value, JobStatus.QUEUED.value
        }

    test_id_options = view.distinct_test_ids(all_rows)
    rows = view.apply_filters(
        all_rows, verdicts=verdicts, error_only=error_only, test_ids=test_ids, q=q
    )
    rows = view.sort_rows(rows, sort, direction)
    filtered = bool(verdicts or error_only or test_ids or q)

    return render_template(
        "detail/index.html",
        meta=meta,
        rows=rows,
        declared_dimensions=dims,
        test_id_options=test_id_options,
        selected={"verdict": verdicts, "test_id": test_ids},
        error_only=error_only,
        q=q,
        sort=sort,
        dir=direction,
        visible_n=len(rows),
        visible_m=len(all_rows),
        filtered=filtered,
        can_cancel=job.status in _CANCELLABLE,
        can_delete=job.status in _DELETABLE,
        can_export=can_export,
        error=None,
    )


@bp.route("/jobs/<job_id>/detail.json", methods=["GET"])
def detail_json(job_id: str):
    """Live state for the poller (FR-015/016); 404 when the job is gone (FR-020)."""
    now = datetime.now(UTC)
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            abort(404)
        meta = view.metadata_view(job, now)
        row_count = UtteranceRepository(session).count_by_job(job_id)
    return jsonify(
        status=meta["status"],
        status_label=meta["status_label"],
        badge_class=meta["badge_class"],
        total=meta["total_utterance_count"],
        processed=meta["processed_count"],
        failed=meta["failed_count"],
        row_count=row_count,
        terminal=meta["terminal"],
    )


@bp.route("/jobs/<job_id>/download.csv", methods=["GET"])
def download_csv(job_id: str):
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            abort(404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = view.reconstruct_csv(job, utterances)
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel(job_id: str):
    with get_session() as session:
        repo = JobRepository(session)
        if repo.get(job_id) is None:
            abort(404)
        try:
            repo.transition_to_cancelling(job_id)
        except InvalidTransitionError:
            return _rerender_error(job_id, "Job is no longer cancellable (already terminal).", 409)
    return redirect(url_for("detail.detail", job_id=job_id))


@bp.route("/jobs/<job_id>/delete", methods=["POST"])
def delete(job_id: str):
    with get_session() as session:
        repo = JobRepository(session)
        job = repo.get(job_id)
        if job is None:
            abort(404)
        if job.status not in _DELETABLE:
            return _rerender_error(
                job_id, f"Job is '{job.status}' and cannot be deleted from this view.", 409
            )
        repo.delete(job_id)
    return redirect(url_for("dashboard.index"))


def _rerender_error(job_id: str, message: str, status_code: int):
    now = datetime.now(UTC)
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            abort(404)
        meta = view.metadata_view(job, now)
        dims = meta["declared_dimensions"]
        rows = [
            view.row_view(u, dims) for u in UtteranceRepository(session).get_by_job_ordered(job_id)
        ]
    return (
        render_template(
            "detail/index.html",
            meta=meta,
            rows=rows,
            declared_dimensions=dims,
            test_id_options=view.distinct_test_ids(rows),
            selected={"verdict": [], "test_id": []},
            error_only=False,
            q="",
            sort="row_index",
            dir="asc",
            visible_n=len(rows),
            visible_m=len(rows),
            filtered=False,
            can_cancel=meta["status"] in _CANCELLABLE,
            can_delete=meta["status"] in _DELETABLE,
            can_export=bool(rows)
            and meta["status"] not in {JobStatus.DRAFT.value, JobStatus.QUEUED.value},
            error=message,
        ),
        status_code,
    )
