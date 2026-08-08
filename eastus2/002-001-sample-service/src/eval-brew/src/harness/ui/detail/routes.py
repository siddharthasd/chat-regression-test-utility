"""Job Detail & Traceability View routes (004/018). The dashboard's row-click target.

Analytics dashboard (018): single-scroll layout with sticky sidebar, Job Overview tiles,
Parameter Breakdown with per-parameter stats + histograms, and Result Explorer table.
Downloads (CSV/JSON) are terminal-only. The old reconstructed-CSV route is removed.
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
from harness.ui.detail.analytics import compute_analytics
from harness.ui.detail.view import (
    _score_label,
    results_csv_builder,
    results_flat_csv_builder,
    results_flat_xlsx_builder,
    results_json_builder,
    results_xlsx_builder,
    score_entries_from_utterances,
)

router = APIRouter()

_CANCELLABLE = {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
_ALWAYS_DELETABLE = {JobStatus.DRAFT.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}
_TERMINAL = {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}

TOOLTIP_COPY = {
    "Mean": (
        "The average score for this parameter across all responses. "
        "Your baseline answer to \"how well did the chatbot perform on this dimension?\""
    ),
    "Median": (
        "The middle score when all responses are ranked from lowest to highest. "
        "If the median is noticeably lower than the mean, a small number of high-scoring "
        "responses are inflating the average. If the median is higher than the mean, a few "
        "poor responses are dragging it down. Mean and median close together means the scores "
        "are consistently spread."
    ),
    "Min": (
        "The lowest score any single response received on this parameter. "
        "Represents the worst-case performance observed in this run."
    ),
    "Max": (
        "The highest score any single response received on this parameter. "
        "Represents the best-case performance observed in this run."
    ),
    "Range": (
        "The gap between the best and worst scores (Max minus Min). A large range means "
        "performance was inconsistent — some responses scored well, others did not. "
        "A small range means the chatbot performed at a similar level across all responses."
    ),
    "σ": (
        "Measures how spread out the scores are around the average. A low σ means most "
        "responses scored close to the mean — predictable, consistent behaviour. A high σ "
        "means scores varied widely — some responses were much better or worse than average. "
        "When comparing two parameters with the same mean, the one with the lower σ is more reliable."
    ),
    "Overall Mean Score": (
        "The average quality score across every response and every evaluation parameter in this run. "
        "Think of it as the overall grade for the chatbot — closer to the evaluator's maximum is better."
    ),
    "Overall Verdict Distribution": (
        "How the evaluator classified each response overall — for example, how many Passed, "
        "how many triggered a Warning, how many Failed. A quick summary of the run's quality at a glance."
    ),
    "Connector Tokens": (
        "Total LLM tokens consumed by all connector calls in this run — the sum of totalTokens "
        "reported by the connector for each row. Rows where the connector did not report token "
        "usage are excluded. Only shown when at least one row reported token counts."
    ),
    "Evaluator Tokens": (
        "Total LLM tokens consumed by all evaluator calls in this run — the sum of totalTokens "
        "reported by the evaluator for each row. Rows where the evaluator did not report token "
        "usage are excluded. Only shown when at least one row reported token counts."
    ),
    "Total Tokens": (
        "Combined connector + evaluator token consumption for this run. "
        "Computed as the sum of each row's connector and evaluator totalTokens. "
        "Only rows that reported token counts contribute to this total."
    ),
}


def _token_totals(utterances: list) -> dict | None:
    """Sum connector/evaluator/total token counts across all utterances.

    Returns None when no row reported any token usage (so the template can skip
    the cards entirely rather than showing three '—' tiles).
    """
    conn_sum = ev_sum = total_sum = 0
    conn_any = ev_any = total_any = False
    for u in utterances:
        r = getattr(u, "evaluation_result", None)
        if r is None:
            continue
        if r.connector_token_count is not None:
            conn_sum += r.connector_token_count
            conn_any = True
        if r.evaluator_token_count is not None:
            ev_sum += r.evaluator_token_count
            ev_any = True
        if r.total_token_count is not None:
            total_sum += r.total_token_count
            total_any = True
    if not (conn_any or ev_any or total_any):
        return None
    return {
        "connector": conn_sum if conn_any else None,
        "evaluator": ev_sum if ev_any else None,
        "total": total_sum if total_any else None,
    }


def _can_delete(job) -> bool:
    """Show Delete button for draft, failed, cancelled, or completed-with-errors."""
    return job.status in _ALWAYS_DELETABLE or (
        job.status == JobStatus.COMPLETED.value and (job.failed_count or 0) > 0
    )


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "on", "yes"}


def _analytics_context(
    utterances: list,
    dims: list[str],
    total_count: int | None = None,
    *,
    score_scale_min: float | None = None,
    score_scale_max: float | None = None,
) -> dict:
    """Shared analytics computation used by job_detail and _rerender_error.

    total_count: use job.total_utterance_count (declared capacity) for the 5K guard;
    falls back to len(utterances) when not available (e.g. in _rerender_error).
    """
    guard_count = total_count if (total_count is not None and total_count > 0) else len(utterances)
    if guard_count > 5000:
        return {"analytics": None, "analytics_skipped": True, "analytics_empty": False}
    entries = score_entries_from_utterances(utterances)
    valid_entries = [e for e in entries if not e.error]
    if not valid_entries:
        return {"analytics": None, "analytics_skipped": False, "analytics_empty": True}
    return {
        "analytics": compute_analytics(
            entries, dims,
            score_scale_min=score_scale_min,
            score_scale_max=score_scale_max,
        ),
        "analytics_skipped": False,
        "analytics_empty": False,
    }


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
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        all_rows = [view.row_view(u, dims) for u in utterances]
        analytics_ctx = _analytics_context(
            utterances, dims, job.total_utterance_count,
            score_scale_min=job.evaluator_score_scale_min,
            score_scale_max=job.evaluator_score_scale_max,
        )
        token_totals = _token_totals(utterances)
        is_terminal = job.status in _TERMINAL
        can_cancel = job.status in _CANCELLABLE
        can_delete = _can_delete(job)
        score_label = _score_label(job.evaluator_score_scale_min, job.evaluator_score_scale_max)

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
            "is_terminal": is_terminal,
            "tooltip_copy": TOOLTIP_COPY,
            "token_totals": token_totals,
            "score_label": score_label,
            "error": None,
            **analytics_ctx,
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


@router.get("/jobs/{job_id}/download-results.csv")
def download_results_csv(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Long-format evaluated results CSV; terminal jobs only (FR-025)."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None or job.status not in _TERMINAL:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = results_csv_builder(job, utterances)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/{job_id}/download-results.json")
def download_results_json(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Nested-by-utterance evaluated results JSON; terminal jobs only (FR-025)."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None or job.status not in _TERMINAL:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = results_json_builder(job, utterances)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/{job_id}/download-results-flat.csv")
def download_results_flat_csv(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """One-row-per-utterance flat CSV with dynamic dimension and source columns (BL-002)."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None or job.status not in _TERMINAL:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = results_flat_csv_builder(job, utterances)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/{job_id}/download-results-flat.xlsx")
def download_results_flat_xlsx(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """One-row-per-utterance flat XLSX with dynamic dimension and source columns (BL-002)."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None or job.status not in _TERMINAL:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = results_flat_xlsx_builder(job, utterances)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/jobs/{job_id}/download-results.xlsx")
def download_results_xlsx(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Multi-sheet XLSX results export (PBI Compatible); terminal jobs only."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None or job.status not in _TERMINAL:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = results_xlsx_builder(job, utterances)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        rows = [view.row_view(u, dims) for u in utterances]
        analytics_ctx = _analytics_context(
            utterances, dims,
            score_scale_min=job.evaluator_score_scale_min,
            score_scale_max=job.evaluator_score_scale_max,
        )
        token_totals = _token_totals(utterances)
        score_label = _score_label(job.evaluator_score_scale_min, job.evaluator_score_scale_max)
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
            "can_delete": _can_delete(job),
            "is_terminal": meta["status"] in _TERMINAL,
            "tooltip_copy": TOOLTIP_COPY,
            "token_totals": token_totals,
            "score_label": score_label,
            "error": message,
            **analytics_ctx,
            **ctx(request),
        },
        status_code=status_code,
    )
