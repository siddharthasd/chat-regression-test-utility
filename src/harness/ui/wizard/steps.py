"""Wizard step-completion predicates, resume-cursor resolver, and the Step 5 review
projection (003 FR-014/015/017). Pure functions over a Job + the two registry readers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness import password_store

if TYPE_CHECKING:
    from harness.connector.registry import ConnectorRegistryReader
    from harness.evaluator.registry import EvaluatorRegistryReader
    from harness.persistence.models import Job


def _registration_active(reader, reg_id: str | None) -> bool:
    """True iff `reg_id` resolves to a present, non-archived registration."""
    if not reg_id:
        return False
    reg = reader.get(reg_id)
    return reg is not None and not reg.archived


def step1_complete(job: Job) -> bool:
    return bool(job.job_name)


def step2_complete(job: Job) -> bool:
    return job.total_utterance_count is not None


def step3_complete(job: Job, conn_reader: ConnectorRegistryReader) -> bool:
    return _registration_active(conn_reader, job.connector_id)


def step4_complete(job: Job, eval_reader: EvaluatorRegistryReader) -> bool:
    return _registration_active(eval_reader, job.evaluation_agent_id)


def password_coordination_ok(job: Job) -> bool:
    """False only when the snapshotted connector wants per-row passwords but the
    in-memory store has no entries for this job (CSV must be re-uploaded). FR-005."""
    if not job.connector_expects_per_row_password:
        return True
    return password_store.job_has_entries(job.job_id)


def lowest_incomplete_step(
    job: Job,
    conn_reader: ConnectorRegistryReader,
    eval_reader: EvaluatorRegistryReader,
) -> int:
    """The step the wizard should open on resume (FR-017): the first incomplete
    step, or 5 when all input steps are complete."""
    if not step1_complete(job):
        return 1
    if not step2_complete(job):
        return 2
    if not step3_complete(job, conn_reader):
        return 3
    if not step4_complete(job, eval_reader):
        return 4
    return 5


def start_ready(
    job: Job,
    conn_reader: ConnectorRegistryReader,
    eval_reader: EvaluatorRegistryReader,
) -> tuple[bool, str | None]:
    """Whether Step 5's Start control is enabled, plus a blocking reason (FR-015)."""
    if not (step1_complete(job) and step2_complete(job)):
        return False, "Job setup is incomplete — finish the earlier steps first."
    if not step3_complete(job, conn_reader):
        return False, "The selected connector is no longer available — re-select one on Step 3."
    if not step4_complete(job, eval_reader):
        return False, "The selected evaluator is no longer available — re-select one on Step 4."
    if not password_coordination_ok(job):
        return False, (
            "The selected connector requires a per-row password column — "
            "re-upload your CSV on Step 2."
        )
    return True, None


def _auth_mode(descriptor: dict | None) -> str:
    return (descriptor or {}).get("mode", "none")


def review_view(job: Job) -> dict:
    """Masked, read-only projection for Step 5 — NEVER includes credential bytes."""
    return {
        "job_id": job.job_id,
        "job_name": job.job_name,
        "description": job.description,
        "total_utterance_count": job.total_utterance_count,
        "source_csv_filename": job.source_csv_filename,
        "connector_name": job.connector_name,
        "connector_endpoint_url": job.connector_endpoint_url,
        "connector_auth_mode": _auth_mode(job.connector_auth_descriptor),
        "connector_expects_per_row_password": job.connector_expects_per_row_password,
        "evaluation_agent_name": job.evaluation_agent_name,
        "evaluator_endpoint_url": job.evaluator_endpoint_url,
        "evaluator_auth_mode": _auth_mode(job.evaluator_auth_descriptor),
        "declared_scoring_dimensions": job.evaluator_declared_scoring_dimensions or [],
    }
