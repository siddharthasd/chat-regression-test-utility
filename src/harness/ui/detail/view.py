"""Detail-view projections: masked metadata, row trace, filters/sort, CSV rebuild (004).

Pure functions over 009 entities. The Job snapshot is the source of truth; secrets
are masked (never decrypted); evaluator-emitted data is returned as plain values
(the template autoescapes it — FR-007a XSS-safe).
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from harness.persistence.enums import JobStatus
from harness.ui.dashboard.view import format_timestamp

if TYPE_CHECKING:
    from harness.persistence.models import Job, Utterance

_MASK = "•" * 8  # ••••••••
_SECRET_SUBFIELDS = ("credential", "password")
_TRUNCATE = 200
_VERDICT_ORDER = {"fail": 0, "warn": 1, "pass": 2}


def mask_descriptor(descriptor: dict | None) -> dict:
    """Copy the stored auth descriptor with secret subfields masked (FR-005). No decryption."""
    if not descriptor:
        return {}
    out = dict(descriptor)
    for key in _SECRET_SUBFIELDS:
        if out.get(key) is not None:
            out[key] = _MASK
    return out


def _badge_class(status: str, failed: int) -> str:
    if status == JobStatus.COMPLETED.value and failed > 0:
        return "badge-completed-errors"
    return f"badge-{status}"


def _status_label(status: str, failed: int) -> str:
    if status == JobStatus.COMPLETED.value and failed > 0:
        return "Completed with errors"
    return status.replace("_", " ").capitalize()


def metadata_view(job: Job, now: datetime | None = None) -> dict:
    """Job Metadata Panel projection (FR-003) — counts are job-level, secrets masked."""
    now = now or datetime.now(UTC)
    failed = job.failed_count or 0
    return {
        "job_id": job.job_id,
        "job_name": job.job_name,
        "description": job.description,
        "status": job.status,
        "status_label": _status_label(job.status, failed),
        "badge_class": _badge_class(job.status, failed),
        "created_by": job.created_by,
        "created_at": format_timestamp(job.created_at, now),
        "started_at": format_timestamp(job.started_at, now),
        "completed_at": format_timestamp(job.completed_at, now),
        "harness_version": job.harness_version,
        "error_details": job.error_details if job.status == JobStatus.FAILED.value else None,
        "connector_name": job.connector_name,
        "connector_id": job.connector_id,
        "connector_endpoint_url": job.connector_endpoint_url,
        "connector_auth": mask_descriptor(job.connector_auth_descriptor),
        "connector_timeout_seconds": job.connector_timeout_seconds,
        "connector_expects_per_row_password": job.connector_expects_per_row_password,
        "evaluation_agent_name": job.evaluation_agent_name,
        "evaluation_agent_id": job.evaluation_agent_id,
        "evaluator_endpoint_url": job.evaluator_endpoint_url,
        "evaluator_auth": mask_descriptor(job.evaluator_auth_descriptor),
        "evaluator_timeout_seconds": job.evaluator_timeout_seconds,
        "declared_dimensions": job.evaluator_declared_scoring_dimensions or [],
        "source_csv_filename": job.source_csv_filename,
        "total_utterance_count": job.total_utterance_count,
        "processed_count": job.processed_count or 0,
        "failed_count": failed,
        "terminal": job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    }


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    return text if len(text) <= _TRUNCATE else text[:_TRUNCATE] + "…"


def _score_cells(result, declared_dims: list[str]) -> list[dict]:
    """Scores ordered by declared dimensions, then any unexpected entries (FR-007b)."""
    if result is None:
        return [{"name": d, "score": "awaiting", "reasoning": ""} for d in declared_dims]
    scores = result.evaluation_scores or []
    by_name = {s.get("parameter_name"): s for s in scores if isinstance(s, dict)}
    cells = []
    for d in declared_dims:
        entry = by_name.get(d)
        if entry is None:
            cells.append({"name": d, "score": "—", "reasoning": ""})
        else:
            cells.append(
                {
                    "name": d,
                    "score": entry.get("score"),
                    "reasoning": entry.get("reasoning") or "(none)",
                }
            )
    for s in scores:
        name = s.get("parameter_name") if isinstance(s, dict) else None
        if name and name not in declared_dims:
            cells.append(
                {"name": name, "score": s.get("score"), "reasoning": s.get("reasoning") or "(none)",
                 "unexpected": True}
            )
    return cells


def row_view(utterance: Utterance, declared_dims: list[str]) -> dict:
    """Results-table row + expand projection (FR-007/008). Never includes password."""
    result = utterance.evaluation_result
    contract = result.normalized_contract if result else None
    response_text = None
    if contract:
        response_text = (contract.get("chatbotResponse") or {}).get("normalizedText")
    annotations = (result.harness_annotations if result else None) or {}
    unexpected = annotations.get("unexpected_score_dimensions") or []
    return {
        "row_index": utterance.row_index,
        "test_id": utterance.test_id,
        "utterance_text": utterance.utterance_text,
        "utterance_text_short": _truncate(utterance.utterance_text),
        "chatbot_response": response_text,
        "chatbot_response_short": _truncate(response_text),
        "verdict": result.evaluation_verdict if result else None,
        "error_status": result.error_status if result else None,
        "error_stage": result.error_stage if result else None,
        "error_details": result.error_details if result else None,
        "scores_cells": _score_cells(result, declared_dims),
        "has_unexpected_dims": bool(unexpected),
        "extra_metadata": utterance.extra_metadata or {},
        # expand artifacts
        "raw_chatbot_response": result.raw_chatbot_response if result else None,
        "normalized_contract": contract,
        "evaluation_scores": result.evaluation_scores if result else None,
        "result_metadata": result.result_metadata if result else None,
        "harness_annotations": annotations or None,
    }


def apply_filters(
    rows: list[dict],
    *,
    verdicts: list[str] | None = None,
    error_only: bool = False,
    test_ids: list[str] | None = None,
    q: str | None = None,
) -> list[dict]:
    """AND-combine verdict/error/testId filters + utterance|response search (FR-013/014)."""
    needle = (q or "").strip().lower()
    out = []
    for r in rows:
        if verdicts and r["verdict"] not in verdicts:
            continue
        if error_only and r["error_status"] != "failed":
            continue
        if test_ids and r["test_id"] not in test_ids:
            continue
        if needle:
            hay = (r["utterance_text"] or "") + "\n" + (r["chatbot_response"] or "")
            if needle not in hay.lower():
                continue
        out.append(r)
    return out


_SORT_KEYS = {
    "row_index": lambda r: r["row_index"],
    "test_id": lambda r: (r["test_id"] or "").lower(),
    "utterance_text": lambda r: (r["utterance_text"] or "").lower(),
    "chatbot_response": lambda r: (r["chatbot_response"] or "").lower(),
    "verdict": lambda r: _VERDICT_ORDER.get(r["verdict"], 99),
    "error_status": lambda r: r["error_status"] or "",
}


def sort_rows(rows: list[dict], sort: str | None, direction: str | None) -> list[dict]:
    """Sort by any column EXCEPT scores (FR-011); default row_index asc."""
    key = _SORT_KEYS.get(sort or "row_index", _SORT_KEYS["row_index"])
    reverse = (direction or "asc").lower() == "desc"
    return sorted(rows, key=key, reverse=reverse)


def distinct_test_ids(rows: list[dict]) -> list[str]:
    return sorted({r["test_id"] for r in rows if r["test_id"]})


def reconstruct_csv(job: Job, utterances: list[Utterance]) -> tuple[str, str]:
    """Rebuild a downloadable CSV from persisted Utterances (FR-006/006a). No password."""
    extra_keys: list[str] = []
    for u in utterances:
        for k in (u.extra_metadata or {}):
            if k not in extra_keys:
                extra_keys.append(k)
    header = ["utteranceText", "testId", *extra_keys]

    buf = io.StringIO()
    terminal = job.status in {
        JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value
    }
    if not terminal:
        buf.write(
            f"# partial download — job is '{job.status}', "
            f"{len(utterances)} row(s) at download\n"
        )
    writer = csv.writer(buf)
    writer.writerow(header)
    for u in utterances:
        extra = u.extra_metadata or {}
        writer.writerow([u.utterance_text, u.test_id, *[extra.get(k, "") for k in extra_keys]])

    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    suffix = "-reconstructed" + ("-partial" if not terminal else "") + ".csv"
    return base + suffix, buf.getvalue()
