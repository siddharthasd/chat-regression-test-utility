"""Job Creation & Configuration Wizard routes (003). Server-rendered Flask blueprint.

The Draft Job IS the wizard state; the current step is derived (lowest-incomplete).
Ties the backend together: Step 2 -> 011 process_upload, Steps 3/4 -> 009 snapshots,
Start -> 012 enqueue_job. No secrets are ever rendered (Step 5 masks to auth mode).
"""

from __future__ import annotations

import os
import tempfile

from flask import Blueprint, abort, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

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
from harness.ui.wizard import steps

bp = Blueprint("wizard", __name__, template_folder="templates")


# --------------------------------------------------------------------------- helpers
def _require_draft_job(session, job_id: str):
    job = JobRepository(session).get(job_id)
    if job is None:
        abort(404)
    return job


def _csv_summary(session, job_id: str) -> dict | None:
    """Recompute the Step-2 summary (count + distinct testIds) from persisted rows."""
    rows = UtteranceRepository(session).get_by_job_ordered(job_id)
    if not rows:
        return None
    return {"utterances": len(rows), "distinct_test_ids": len({r.test_id for r in rows})}


# ------------------------------------------------------------------------------ clone
@bp.route("/jobs/<job_id>/clone", methods=["POST"])
def clone_job(job_id: str):
    """Clone a terminal job into a new draft, re-snapshotting from the live registry."""
    from harness.ui.detail import view as detail_view

    with get_session() as session:
        source = JobRepository(session).get(job_id)
        if source is None:
            abort(404)

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

    # Process CSV before setting the connector snapshot so that the password-column
    # requirement (connector_expects_per_row_password) doesn't apply to the
    # reconstructed CSV, which never contains passwords.
    if csv_str:
        fd, tmp_path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(csv_str)
            process_upload(new_job_id, tmp_path, filename=source_csv_filename)
        finally:
            os.unlink(tmp_path)

    # Re-snapshot connector and evaluator from the live registry so any credential
    # fixes the user applied since the original run are picked up automatically.
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

    # Resume derives the lowest-incomplete step automatically; if everything is
    # still active it lands on step 5 (review) ready to start immediately.
    return redirect(url_for("wizard.resume", job_id=new_job_id))


# ------------------------------------------------------------------------ create/resume
@bp.route("/jobs/new", methods=["GET"])
def new_job():
    return render_template("wizard/step1.html", job=None, error=None, form={})


@bp.route("/jobs", methods=["POST"])
def create_job():
    name = (request.form.get("job_name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    if not name:
        return (
            render_template(
                "wizard/step1.html", job=None, error="Job name is required.", form=request.form
            ),
            400,
        )
    with get_session() as session:
        created_by = IdentityContext.current().value
        job = JobRepository(session).create_draft(name, description, created_by)
        job_id = job.job_id
    return redirect(url_for("wizard.step2", job_id=job_id))


@bp.route("/jobs/<job_id>", methods=["GET"])
def resume(job_id: str):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        step = steps.lowest_incomplete_step(
            job, ConnectorRegistryReader(session), EvaluatorRegistryReader(session)
        )
    return redirect(url_for(f"wizard.step{step}", job_id=job_id))


# ------------------------------------------------------------------------------- step 1
@bp.route("/jobs/<job_id>/step1", methods=["GET"])
def step1(job_id: str):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        form = {"job_name": job.job_name, "description": job.description or ""}
    return render_template("wizard/step1.html", job=job, error=None, form=form)


@bp.route("/jobs/<job_id>/step1", methods=["POST"])
def step1_save(job_id: str):
    name = (request.form.get("job_name") or "").strip()
    description = (request.form.get("description") or "").strip() or None
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        if not name:
            return (
                render_template(
                    "wizard/step1.html", job=job, error="Job name is required.", form=request.form
                ),
                400,
            )
        job.job_name = name
        job.description = description
    return redirect(url_for("wizard.step2", job_id=job_id))


# ------------------------------------------------------------------------------- step 2
@bp.route("/jobs/<job_id>/step2", methods=["GET"])
def step2(job_id: str):
    notice = request.args.get("notice")
    with get_session() as session:
        _require_draft_job(session, job_id)
        summary = _csv_summary(session, job_id)
    return render_template(
        "wizard/step2.html", job_id=job_id, summary=summary, errors=None, notice=notice
    )


@bp.route("/jobs/<job_id>/step2", methods=["POST"])
def step2_upload(job_id: str):
    upload = request.files.get("csv_file")
    if upload is None or not upload.filename:
        return (
            render_template(
                "wizard/step2.html",
                job_id=job_id,
                summary=None,
                errors=[{"message": "Choose a CSV file to upload."}],
                notice=None,
            ),
            400,
        )

    filename = secure_filename(upload.filename) or "upload.csv"
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as fh:
            upload.save(fh)
        result = process_upload(job_id, tmp_path, filename=filename)
    finally:
        os.unlink(tmp_path)

    if not result.success:
        errors = [
            {"category": str(e.category), "row": e.row, "column": e.column, "message": e.message}
            for e in result.errors
        ]
        return (
            render_template(
                "wizard/step2.html", job_id=job_id, summary=None, errors=errors, notice=None
            ),
            400,
        )
    return redirect(url_for("wizard.step3", job_id=job_id))


# ------------------------------------------------------------------------------- step 3
@bp.route("/jobs/<job_id>/step3", methods=["GET"])
def step3(job_id: str):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        entries = ConnectorRegistryReader(session).list_active()
        selected = job.connector_id
    return render_template(
        "wizard/step3.html", job_id=job_id, entries=entries, selected=selected, error=None
    )


@bp.route("/jobs/<job_id>/step3", methods=["POST"])
def step3_save(job_id: str):
    connector_id = (request.form.get("connector_id") or "").strip()
    with get_session() as session:
        _require_draft_job(session, job_id)
        reader = ConnectorRegistryReader(session)
        reg = reader.get(connector_id) if connector_id else None
        if reg is None or reg.archived:
            return (
                render_template(
                    "wizard/step3.html",
                    job_id=job_id,
                    entries=reader.list_active(),
                    selected=None,
                    error="Select an active connector to continue.",
                ),
                400,
            )
        JobRepository(session).set_connector_snapshot(job_id, reg)
        expects = reg.expects_per_row_password

    # Per-row-password coordination (FR-005): a password-requiring connector needs a
    # CSV that staged passwords; if none, the tester must re-upload at Step 2.
    if expects and not steps.password_store.job_has_entries(job_id):
        return redirect(
            url_for(
                "wizard.step2",
                job_id=job_id,
                notice="The selected connector requires a per-row 'password' column. "
                "Please re-upload your CSV.",
            )
        )
    return redirect(url_for("wizard.step4", job_id=job_id))


# ------------------------------------------------------------------------------- step 4
@bp.route("/jobs/<job_id>/step4", methods=["GET"])
def step4(job_id: str):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        entries = EvaluatorRegistryReader(session).list_active()
        selected = job.evaluation_agent_id
    return render_template(
        "wizard/step4.html", job_id=job_id, entries=entries, selected=selected, error=None
    )


@bp.route("/jobs/<job_id>/step4", methods=["POST"])
def step4_save(job_id: str):
    agent_id = (request.form.get("evaluation_agent_id") or "").strip()
    with get_session() as session:
        _require_draft_job(session, job_id)
        reader = EvaluatorRegistryReader(session)
        reg = reader.get(agent_id) if agent_id else None
        if reg is None or reg.archived:
            return (
                render_template(
                    "wizard/step4.html",
                    job_id=job_id,
                    entries=reader.list_active(),
                    selected=None,
                    error="Select an active evaluator to continue.",
                ),
                400,
            )
        JobRepository(session).set_evaluator_snapshot(job_id, reg)
    return redirect(url_for("wizard.step5", job_id=job_id))


# ------------------------------------------------------------------------------- step 5
@bp.route("/jobs/<job_id>/step5", methods=["GET"])
def step5(job_id: str):
    with get_session() as session:
        job = _require_draft_job(session, job_id)
        view = steps.review_view(job)
        ready, reason = steps.start_ready(
            job, ConnectorRegistryReader(session), EvaluatorRegistryReader(session)
        )
        view["distinct_test_ids"] = (_csv_summary(session, job_id) or {}).get("distinct_test_ids")
    return render_template(
        "wizard/step5.html", job_id=job_id, view=view, start_ready=ready, reason=reason, error=None
    )


@bp.route("/jobs/<job_id>/start", methods=["POST"])
def start(job_id: str):
    try:
        with get_session() as session:
            JobRepository(session).transition_to_queued(job_id)
    except (MissingSnapshotFieldError, InactiveRegistrationError, InvalidTransitionError) as exc:
        with get_session() as session:
            job = _require_draft_job(session, job_id)
            view = steps.review_view(job)
            view["distinct_test_ids"] = (_csv_summary(session, job_id) or {}).get(
                "distinct_test_ids"
            )
        return (
            render_template(
                "wizard/step5.html",
                job_id=job_id,
                view=view,
                start_ready=False,
                reason=None,
                error=f"Could not start the job: {exc}",
            ),
            409,
        )
    enqueue_job(job_id)
    return redirect(url_for("wizard.started", job_id=job_id))


@bp.route("/jobs/<job_id>/started", methods=["GET"])
def started(job_id: str):
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            abort(404)
        view = {"job_id": job.job_id, "job_name": job.job_name, "status": job.status}
    return render_template("wizard/started.html", view=view)
