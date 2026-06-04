"""Results export builder (005). Pure on-demand CSV/JSON/zip generation.

Projects one Job + its Utterances/EvaluationResults into a downloadable artifact.
Passwords are never emitted (key omitted); credential subfields are masked via the
same helper the detail view uses (never decrypted). See contracts/export-api.md.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from harness.persistence.enums import JobStatus
from harness.ui.detail.view import mask_descriptor

if TYPE_CHECKING:
    from harness.persistence.models import Job, Utterance

FORMATS = ("csv", "json", "zip")
_NONTERMINAL = {JobStatus.RUNNING.value, JobStatus.CANCELLING.value}
#: Per-row fields that hold structured data — JSON-stringified in CSV cells (FR-008).
_NESTED_FIELDS = (
    "rawChatbotResponse",
    "normalizedContract",
    "evaluationScores",
    "metadata",
    "harnessAnnotations",
)


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def job_metadata(job: Job, exported_at: datetime) -> dict:
    """Job-level metadata block (FR-005). Descriptors masked; never decrypted."""
    return {
        "jobId": job.job_id,
        "jobName": job.job_name,
        "description": job.description or "",
        "createdBy": job.created_by,
        "createdAt": _iso(job.created_at),
        "startedAt": _iso(job.started_at),
        "completedAt": _iso(job.completed_at),
        "status": job.status,
        "harnessVersion": job.harness_version,
        "sourceCSVFilename": job.source_csv_filename or "",
        "errorDetails": job.error_details if job.status == JobStatus.FAILED.value else "",
        "connectorId": job.connector_id or "",
        "connectorName": job.connector_name or "",
        "connectorEndpointUrl": job.connector_endpoint_url or "",
        "connectorAuthDescriptor": mask_descriptor(job.connector_auth_descriptor),
        "connectorTimeoutSeconds": job.connector_timeout_seconds,
        "connectorExpectsPerRowPassword": job.connector_expects_per_row_password,
        "evaluationAgentId": job.evaluation_agent_id or "",
        "evaluationAgentName": job.evaluation_agent_name or "",
        "evaluatorEndpointUrl": job.evaluator_endpoint_url or "",
        "evaluatorAuthDescriptor": mask_descriptor(job.evaluator_auth_descriptor),
        "evaluatorTimeoutSeconds": job.evaluator_timeout_seconds,
        "evaluatorDeclaredScoringDimensions": job.evaluator_declared_scoring_dimensions or [],
        "totalUtteranceCount": job.total_utterance_count,
        "processedCount": job.processed_count or 0,
        "failedCount": job.failed_count or 0,
        "exportedAt": exported_at.isoformat(),
        "partial": job.status in _NONTERMINAL,
    }


def _ordered_scores(scores: list | None, declared_dims: list[str]) -> list:
    """Declared-dimension order first, then unexpected entries in emitted order (FR-006a)."""
    if not scores:
        return []
    by_name: dict[str, dict] = {}
    extras: list = []
    for s in scores:
        name = s.get("parameter_name") if isinstance(s, dict) else None
        if name in declared_dims and name not in by_name:
            by_name[name] = s
        else:
            extras.append(s)
    ordered = [by_name[d] for d in declared_dims if d in by_name]
    return ordered + extras


def row_record(utterance: Utterance, declared_dims: list[str]) -> dict:
    """Per-row export block (FR-006). No password / userFeedback / top-level reasoning."""
    r = utterance.evaluation_result
    return {
        "utteranceId": utterance.utterance_id,
        "rowIndex": utterance.row_index,
        "utteranceText": utterance.utterance_text,
        "testId": utterance.test_id,
        "rawChatbotResponse": r.raw_chatbot_response if r else None,
        "normalizedContract": r.normalized_contract if r else None,
        "evaluationVerdict": r.evaluation_verdict if r else None,
        "evaluationScores": _ordered_scores(r.evaluation_scores if r else None, declared_dims),
        "metadata": r.result_metadata if r else None,
        "harnessAnnotations": (r.harness_annotations if r else None) or {},
        "evaluationAgentId": r.evaluation_agent_id if r else None,
        "errorStatus": r.error_status if r else None,
        "errorStage": r.error_stage if r else None,
        "errorDetails": r.error_details if r else None,
        "evaluationTimestamp": _iso(r.evaluation_timestamp) if r else "",
    }


def _records(job: Job, utterances: list[Utterance]) -> tuple[dict, list[dict]]:
    exported_at = datetime.now(UTC)
    meta = job_metadata(job, exported_at)
    dims = job.evaluator_declared_scoring_dimensions or []
    rows = [row_record(u, dims) for u in utterances]
    return meta, rows


def build_json(meta: dict, rows: list[dict]) -> bytes:
    payload = {"job": meta, "rows": rows, "partial": meta["partial"]}
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def build_csv(meta: dict, rows: list[dict]) -> bytes:
    """Rectangular: repeated metadata columns + per-row columns (FR-007/008)."""
    meta_keys = list(meta.keys())
    row_keys = list(rows[0].keys()) if rows else list(row_record_keys())
    header = meta_keys + row_keys

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    meta_cells = [_csv_cell(meta[k]) for k in meta_keys]
    for r in rows:
        writer.writerow(meta_cells + [_csv_cell(r[k], k) for k in row_keys])
    return buf.getvalue().encode("utf-8")


def row_record_keys() -> tuple[str, ...]:
    """Stable per-row column order (used when a job has zero rows)."""
    return (
        "utteranceId", "rowIndex", "utteranceText", "testId", "rawChatbotResponse",
        "normalizedContract", "evaluationVerdict", "evaluationScores", "metadata",
        "harnessAnnotations", "evaluationAgentId", "errorStatus", "errorStage",
        "errorDetails", "evaluationTimestamp",
    )


def _csv_cell(value: object, key: str | None = None) -> str:
    if value is None:
        return ""
    if key in _NESTED_FIELDS or isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def build_zip(meta: dict, rows: list[dict], base: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}.csv", build_csv(meta, rows))
        zf.writestr(f"{base}.json", build_json(meta, rows))
    return buf.getvalue()


def _slug(job: Job) -> str:
    raw = job.job_name or f"job-{job.job_id[:8]}"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-").lower()
    return slug or f"job-{job.job_id[:8]}"


def build_export(
    job: Job, utterances: list[Utterance], fmt: str, *, exported_at: datetime | None = None
) -> tuple[str, str, bytes]:
    """Build a downloadable export. Returns (filename, mimetype, body)."""
    if fmt not in FORMATS:
        fmt = "csv"
    meta, rows = _records(job, utterances)
    if exported_at is not None:
        meta["exportedAt"] = exported_at.isoformat()

    partial = "-partial" if meta["partial"] else ""
    base = f"{_slug(job)}-results{partial}"

    if fmt == "json":
        return f"{base}.json", "application/json", build_json(meta, rows)
    if fmt == "zip":
        return f"{base}.zip", "application/zip", build_zip(meta, rows, base)
    return f"{base}.csv", "text/csv", build_csv(meta, rows)
