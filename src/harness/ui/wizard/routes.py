"""Job Creation & Configuration Wizard routes (003). Server-rendered FastAPI router.

The Draft Job IS the wizard state; the current step is derived (lowest-incomplete).
Ties the backend together: Step 2 -> 011 process_upload, Steps 3/4 -> 009 snapshots,
Start -> 012 enqueue_job. No secrets are ever rendered (Step 5 masks to auth mode).
"""

from __future__ import annotations

import os
import re
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse

from harness.auth.middleware import require_auth
from harness.connector.registry import ConnectorRegistryReader
from harness.csv_upload import process_upload
from harness.evaluator.registry import EvaluatorRegistryReader
from harness.identity.context import IdentityContext
from harness.orchestrator import enqueue_job  # module global — patchable in tests
from harness.persistence import get_session
from harness.persistence.exceptions import (
    InactiveRegistrationError,
    InvalidTransitionError,
    MissingSnapshotFieldError,
)
from harness.persistence.repositories import JobRepository, UtteranceRepository
from harness.ui._context import ctx
from harness.ui._templates import templates
from harness.ui.wizard import steps

router = APIRouter()


# --------------------------------------------------------------------------- helpers
def _secure_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    return re.sub(r"[^\w.\-]", "_", name).strip("._")


def _require_draft_job(session, job_id: str):
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404)
    return job


def _csv_summary(session, job_id: str) -> dict | None:
    """Recompute the Step-2 summary (count + distinct testIds) from persisted rows."""
    rows = UtteranceRepository(session).get_by_job_ordered(job_id)
    if not rows:
        return None
    return {"utterances": len(rows), "distinct_test_ids": len({r.test_id for r in rows})}


# ------------------------------------------------------------------------------ clone
@router.post("/jobs/{job_id}/clone")
def clone_job(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Clone a terminal job into a new draft, re-snapshotting from the live registry."""
    from harness.ui.detail import view as detail_view

    with get_session() as session:
        source = JobRepository(session).get(job_id)
        if source is None:
            raise HTTPException(status_code=404)

        created_by = IdentityContext.current().value
        new_job = JobRepository(session).create_draft(
            f"{source.job_name} (retry)", source.description, created_by
        )
        new_job_id = new_job.job_id

        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        source_csv_filename = source.source_csv_filename or f"job-{job_id[:8]}.csv"
        csv_str = detail_view.reconstruct_csv(source, utterances)[1] if utterances else None
        source_connector_id = source.connector_id
        source_evaluator_id = source.evaluation_agent_id

    if csv_str:
        fd, tmp_path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(csv_str)
            process_upload(new_job_id, tmp_path, filename=source_csv_filename)
        finally:
            os.unlink(tmp_path)

    with get_session() as session:
        repo = JobRepository(session)
        if source_connector_id:
            reg = ConnectorRegistryReader(session).get(source_connector_id)
            if reg and not reg.archived:
                repo.set_connector_snapshot(new_job_id, reg)
        if source_evaluator_id:
            reg = EvaluatorRegistryReader(session).get(source_evaluator_id)
            if reg and not reg.archived:
                repo.set_evaluator_snapshot(new_job_id, reg)

    return RedirectResponse(request.url_for("resume", job_id=new_job_id), status_code=303)


# ------------------------------------------------------------------------ create/resume
@router.get("/jobs/new")
def new_job(request: Request, user: dict = Depends(require_auth)):
    return templates.TemplateResponse(
        request, "wizard/step1.html", {"job": None, "error": None, "form": {}, **ctx(request)}
    )


@router.post("/jobs")
def create_job(
    request: Request,
    job_name: str = Form(None),
    description: str = Form(None),
    user: dict = Depends(require_auth),
):
    name = (job_name or "").strip()
    desc = (description or "").strip() or None
    if not name:
        return templates.TemplateResponse(
            request,
            "wizard/step1.html",
            {
                "job": None,
                "error": "Job name is required.",
                "form": {"job_name": job_name, "description": description},
                **ctx(request),
            },
            status_code=400,
        )
    with get_session() as session:
        created_by = IdentityContext.current().value
        job = JobRepository(session).create_draft(name, desc, created_by)
        job_id = job.job_id
    return RedirectResponse(request.url_for("step2", job_id=job_id), status_code=303)


@router.get("/jobs/{job_id}")
def resume(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        step = steps.lowest_incomplete_step(
            job, ConnectorRegistryReader(session), EvaluatorRegistryReader(session)
        )
    step_url = request.url_for(f"step{step}", job_id=job_id)
    return RedirectResponse(step_url, status_code=303)


# ------------------------------------------------------------------------------- step 1
@router.get("/jobs/{job_id}/step1")
def step1(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        form = {"job_name": job.job_name, "description": job.description or ""}
    return templates.TemplateResponse(
        request, "wizard/step1.html", {"job": job, "error": None, "form": form, **ctx(request)}
    )


@router.post("/jobs/{job_id}/step1")
def step1_save(
    request: Request,
    job_id: str,
    job_name: str = Form(None),
    description: str = Form(None),
    user: dict = Depends(require_auth),
):
    name = (job_name or "").strip()
    desc = (description or "").strip() or None
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        if not name:
            return templates.TemplateResponse(
                request,
                "wizard/step1.html",
                {
                    "job": job,
                    "error": "Job name is required.",
                    "form": {"job_name": job_name, "description": description},
                    **ctx(request),
                },
                status_code=400,
            )
        job.job_name = name
        job.description = desc
    return RedirectResponse(request.url_for("step2", job_id=job_id), status_code=303)


# ------------------------------------------------------------------------------- step 2
@router.get("/jobs/{job_id}/step2")
def step2(
    request: Request,
    job_id: str,
    notice: str = Query(None),
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        _require_draft_job(session, job_id)
        summary = _csv_summary(session, job_id)
    return templates.TemplateResponse(
        request,
        "wizard/step2.html",
        {"job_id": job_id, "summary": summary, "errors": None, "notice": notice, **ctx(request)},
    )


@router.post("/jobs/{job_id}/step2")
def step2_upload(
    request: Request,
    job_id: str,
    csv_file: UploadFile = File(None),
    user: dict = Depends(require_auth),
):
    if csv_file is None or not csv_file.filename:
        return templates.TemplateResponse(
            request,
            "wizard/step2.html",
            {
                "job_id": job_id,
                "summary": None,
                "errors": [{"message": "Choose a CSV file to upload."}],
                "notice": None,
                **ctx(request),
            },
            status_code=400,
        )

    filename = _secure_filename(csv_file.filename or "") or "upload.csv"
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(csv_file.file.read())
        result = process_upload(job_id, tmp_path, filename=filename)
    finally:
        os.unlink(tmp_path)

    if not result.success:
        errors = [
            {"category": str(e.category), "row": e.row, "column": e.column, "message": e.message}
            for e in result.errors
        ]
        return templates.TemplateResponse(
            request,
            "wizard/step2.html",
            {"job_id": job_id, "summary": None, "errors": errors, "notice": None, **ctx(request)},
            status_code=400,
        )
    return RedirectResponse(request.url_for("step3", job_id=job_id), status_code=303)


# ------------------------------------------------------------------------------- step 3
@router.get("/jobs/{job_id}/step3")
def step3(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        entries = ConnectorRegistryReader(session).list_active()
        selected = job.connector_id
    return templates.TemplateResponse(
        request,
        "wizard/step3.html",
        {"job_id": job_id, "entries": entries, "selected": selected, "error": None, **ctx(request)},
    )


@router.post("/jobs/{job_id}/step3")
def step3_save(
    request: Request,
    job_id: str,
    connector_id: str = Form(None),
    user: dict = Depends(require_auth),
):
    cid = (connector_id or "").strip()
    with get_session() as session:
        _require_draft_job(session, job_id)
        reader = ConnectorRegistryReader(session)
        reg = reader.get(cid) if cid else None
        if reg is None or reg.archived:
            return templates.TemplateResponse(
                request,
                "wizard/step3.html",
                {
                    "job_id": job_id,
                    "entries": reader.list_active(),
                    "selected": None,
                    "error": "Select an active connector to continue.",
                    **ctx(request),
                },
                status_code=400,
            )
        JobRepository(session).set_connector_snapshot(job_id, reg)
        expects = reg.expects_per_row_password

    if expects and not steps.password_store.job_has_entries(job_id):
        notice_msg = (
            "The selected connector requires a per-row 'password' column. "
            "Please re-upload your CSV."
        )
        step2_url = str(request.url_for("step2", job_id=job_id)) + f"?notice={notice_msg}"
        return RedirectResponse(step2_url, status_code=303)
    return RedirectResponse(request.url_for("step4", job_id=job_id), status_code=303)


# ------------------------------------------------------------------------------- step 4
@router.get("/jobs/{job_id}/step4")
def step4(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        entries = EvaluatorRegistryReader(session).list_active()
        selected = job.evaluation_agent_id
    return templates.TemplateResponse(
        request,
        "wizard/step4.html",
        {"job_id": job_id, "entries": entries, "selected": selected, "error": None, **ctx(request)},
    )


@router.post("/jobs/{job_id}/step4")
def step4_save(
    request: Request,
    job_id: str,
    evaluation_agent_id: str = Form(None),
    user: dict = Depends(require_auth),
):
    agent_id = (evaluation_agent_id or "").strip()
    with get_session() as session:
        _require_draft_job(session, job_id)
        reader = EvaluatorRegistryReader(session)
        reg = reader.get(agent_id) if agent_id else None
        if reg is None or reg.archived:
            return templates.TemplateResponse(
                request,
                "wizard/step4.html",
                {
                    "job_id": job_id,
                    "entries": reader.list_active(),
                    "selected": None,
                    "error": "Select an active evaluator to continue.",
                    **ctx(request),
                },
                status_code=400,
            )
        JobRepository(session).set_evaluator_snapshot(job_id, reg)
    return RedirectResponse(request.url_for("step5", job_id=job_id), status_code=303)


# ------------------------------------------------------------------------------- step 5
@router.get("/jobs/{job_id}/step5")
def step5(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        step_view = steps.review_view(job)
        ready, reason = steps.start_ready(
            job, ConnectorRegistryReader(session), EvaluatorRegistryReader(session)
        )
        step_view["distinct_test_ids"] = (_csv_summary(session, job_id) or {}).get(
            "distinct_test_ids"
        )
    return templates.TemplateResponse(
        request,
        "wizard/step5.html",
        {
            "job_id": job_id,
            "view": step_view,
            "start_ready": ready,
            "reason": reason,
            "error": None,
            **ctx(request),
        },
    )


@router.post("/jobs/{job_id}/start")
def start(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    try:
        with get_session() as session:
            JobRepository(session).transition_to_queued(job_id)
    except (MissingSnapshotFieldError, InactiveRegistrationError, InvalidTransitionError) as exc:
        with get_session() as session:
            job = _require_draft_job(session, job_id)
            step_view = steps.review_view(job)
            step_view["distinct_test_ids"] = (_csv_summary(session, job_id) or {}).get(
                "distinct_test_ids"
            )
        return templates.TemplateResponse(
            request,
            "wizard/step5.html",
            {
                "job_id": job_id,
                "view": step_view,
                "start_ready": False,
                "reason": None,
                "error": f"Could not start the job: {exc}",
                **ctx(request),
            },
            status_code=409,
        )
    enqueue_job(job_id)
    return RedirectResponse(request.url_for("started", job_id=job_id), status_code=303)


@router.get("/jobs/{job_id}/started")
def started(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            raise HTTPException(status_code=404)
        job_view = {"job_id": job.job_id, "job_name": job.job_name, "status": job.status}
    return templates.TemplateResponse(
        request, "wizard/started.html", {"view": job_view, **ctx(request)}
    )
