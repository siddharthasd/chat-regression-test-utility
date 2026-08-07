"""Detail-view projections: masked metadata, row trace, filters/sort, CSV rebuild (004).

Pure functions over 009 entities. The Job snapshot is the source of truth; secrets
are masked (never decrypted); evaluator-emitted data is returned as plain values
(the template autoescapes it — FR-007a XSS-safe).
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import openpyxl
from openpyxl.cell.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from harness.persistence.enums import JobStatus
from harness.ui.dashboard.view import format_timestamp

if TYPE_CHECKING:
    from harness.persistence.models import Job, Utterance

from harness.ui.detail.analytics import ScoreEntry

_MASK = "•" * 8  # ••••••••
_SECRET_SUBFIELDS = ("credential", "password")
_TRUNCATE = 200
_VERDICT_ORDER = {"fail": 0, "warn": 1, "pass": 2}
_ERROR_STATUSES = frozenset({"failed", "cancelled"})

# BL-003: stakeholder-friendly column header mapping.
# Maps internal engineering names → display labels used in all CSV/XLSX exports.
# Dynamic flat columns ({name}_score / source{N}_title etc.) are handled by _friendly().
_HEADER_MAP: dict[str, str] = {
    "utteranceText":   "User Question",
    "testId":          "Test Case Reference",
    "utteranceIntent": "Intent Category",
    "chatbotResponse": "Chatbot Answer",
    "overallVerdict":  "Overall Result",
    "utteranceId":     "Row ID",
    # Long-format per-dim columns
    "parameterName":   "Dimension",
    "score":           "Score (0–1)",
    "verdict":         "Result",
    "reasoning":       "Justification",
    # Long-format and Sheet 2 source columns
    "sourceIndex":     "Source #",
    "title":           "Source Title",
    "url":             "Source URL",
    "documentId":      "Document ID",
    "scope":           "Scope",
    "chunk":           "Retrieved Text",
}

_SRC_FIELD_LABEL: dict[str, str] = {
    "title":      "Title",
    "url":        "URL",
    "documentId": "Document ID",
    "scope":      "Scope",
    "chunk":      "Retrieved Text",
}

# Module-level XLSX style singletons — created once, reused across all builders.
_BOLD = Font(bold=True)
_FILL = PatternFill("solid", fgColor="DDEEFF")
_SECTION_FONT = Font(bold=True, size=12)


def _set_ws_widths(ws, widths: list[int]) -> None:
    """Set column widths on a write-only worksheet."""
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_header_row(ws, values: list, fill: bool = False) -> None:
    """Append a bold (optionally filled) header row to a write-only worksheet."""
    cells = []
    for v in values:
        c = WriteOnlyCell(ws, value=v)
        c.font = _BOLD
        if fill:
            c.fill = _FILL
        cells.append(c)
    ws.append(cells)


def _friendly(col: str) -> str:
    """Return the stakeholder-friendly label for an internal column name."""
    if col in _HEADER_MAP:
        return _HEADER_MAP[col]
    # Dynamic flat dim columns: {name}_score / {name}_verdict / {name}_reasoning
    for suffix, label in (
        ("_score",     ": Score (0–1)"),
        ("_verdict",   ": Result"),
        ("_reasoning", ": Justification"),
    ):
        if col.endswith(suffix):
            return col[: -len(suffix)] + label
    # Dynamic flat source columns: source{N}_field
    m = re.match(r"^source(\d+)_(\w+)$", col)
    if m:
        n, field = m.group(1), m.group(2)
        return f"Source {n}: {_SRC_FIELD_LABEL.get(field, field)}"
    return col


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


def _extract_sources(contract: dict | None) -> list[dict]:
    """Extract chatbotResponse.metadata.sources; normalise each entry; return [] on any error."""
    raw = (
        (contract or {})
        .get("chatbotResponse", {})
        .get("metadata", {})
        .get("sources") or []
    )
    if not isinstance(raw, list):
        return []
    result = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        chunk = s.get("chunk") or ""
        url = s.get("url") or ""
        if url and not url.startswith(("http://", "https://")):
            url = ""
        result.append({
            "url": url,
            "title": s.get("title") or "",
            "chunk": chunk,
            "chunk_short": chunk[:_TRUNCATE] + "…" if len(chunk) > _TRUNCATE else chunk,
            "scope": s.get("scope") or "",
            "documentId": s.get("documentId") or "",
        })
    return result


def _long_format_rows(utterances):
    """Yield one row list per (utterance × dimension × source) cross-product.

    Used by both results_csv_builder and results_xlsx_builder (Sheet 1) to
    eliminate duplicated cross-product logic between the two builders.
    """
    for u in utterances:
        result = u.evaluation_result
        contract = result.normalized_contract if result else None
        response_text = (
            (contract.get("chatbotResponse") or {}).get("normalizedText") or ""
            if contract else ""
        )
        overall_verdict = (result.evaluation_verdict if result else None) or ""
        intent = (result.utterance_intent if result else None) or ""
        scores = (result.evaluation_scores or []) if result else []
        sources = _extract_sources(contract)

        dim_rows: list[tuple] = []
        for s in scores:
            if isinstance(s, dict):
                dim_rows.append((
                    s.get("parameter_name", ""), s.get("score", ""),
                    s.get("verdict") or "", s.get("reasoning", ""),
                ))
        if not dim_rows:
            dim_rows = [("", "", "", "")]

        src_rows = list(enumerate(sources, start=1)) if sources else [(0, None)]

        for dim in dim_rows:
            for idx, src in src_rows:
                src_fields = (
                    ["", "", "", "", "", ""] if src is None
                    else [idx, src["title"], src["url"], src["documentId"], src["scope"], src["chunk"]]
                )
                yield [
                    u.utterance_text, u.test_id or "", intent, response_text, overall_verdict,
                    *dim, *src_fields,
                ]


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
            cells.append({"name": d, "score": "—", "reasoning": "", "verdict": None})
        else:
            cells.append(
                {
                    "name": d,
                    "score": entry.get("score"),
                    "reasoning": entry.get("reasoning") or "(none)",
                    "verdict": entry.get("verdict"),
                }
            )
    for s in scores:
        name = s.get("parameter_name") if isinstance(s, dict) else None
        if name and name not in declared_dims:
            cells.append(
                {
                    "name": name,
                    "score": s.get("score"),
                    "reasoning": s.get("reasoning") or "(none)",
                    "verdict": s.get("verdict"),
                    "unexpected": True,
                }
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
    sources = _extract_sources(contract)
    return {
        "row_index": utterance.row_index,
        "test_id": utterance.test_id,
        "utterance_text": utterance.utterance_text,
        "utterance_text_short": _truncate(utterance.utterance_text),
        "chatbot_response": response_text,
        "chatbot_response_short": _truncate(response_text),
        "verdict": result.evaluation_verdict if result else None,
        "utterance_intent": result.utterance_intent if result else None,
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
        # retrieved context (BL-001)
        "source_count": len(sources),
        "sources": sources,
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
        if error_only and r["error_status"] not in _ERROR_STATUSES:
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


def score_entries_from_utterances(utterances: list) -> list[ScoreEntry]:
    """Map ORM Utterance list to ScoreEntry list for the RunAnalytics engine."""
    entries = []
    for u in utterances:
        result = u.evaluation_result
        is_error = bool(result and result.error_status in _ERROR_STATUSES) or result is None
        overall_verdict = result.evaluation_verdict if result else None
        intent = result.utterance_intent if result else None
        scores = (result.evaluation_scores or []) if result else []
        for s in scores:
            if not isinstance(s, dict):
                continue
            entries.append(
                ScoreEntry(
                    parameter_name=s.get("parameter_name", ""),
                    score=float(s.get("score") or 0.0),
                    reasoning=s.get("reasoning") or "",
                    verdict=s.get("verdict"),
                    overall_verdict=overall_verdict,
                    error=is_error,
                    unit_id=str(u.utterance_id),
                    utterance_intent=intent,
                )
            )
        if not scores:
            # Sentinel: utterance with no score entries — still counts toward
            # evaluated_count (non-error) or error_count (error) via unit_id.
            entries.append(
                ScoreEntry(
                    parameter_name="",
                    score=0.0,
                    reasoning="",
                    verdict=None,
                    overall_verdict=overall_verdict,
                    error=is_error,
                    unit_id=str(u.utterance_id),
                    utterance_intent=intent,
                )
            )
    return entries


def results_csv_builder(job: Job, utterances: list) -> tuple[str, str]:
    """Build long-format evaluated results CSV. Returns (filename, csv_body).

    Rows are the cross-product of evaluation dimensions × retrieved sources.
    Utterances with no sources emit one row per dimension with blank source fields.
    """
    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    filename = f"{base}-results.csv"

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([_friendly(c) for c in (
        "utteranceText", "testId", "utteranceIntent", "chatbotResponse", "overallVerdict",
        "parameterName", "score", "verdict", "reasoning",
        "sourceIndex", "title", "url", "documentId", "scope", "chunk",
    )])
    for row in _long_format_rows(utterances):
        writer.writerow(row)
    return filename, buf.getvalue()


def results_json_builder(job: Job, utterances: list) -> tuple[str, str]:
    """Build nested-by-utterance results JSON. Returns (filename, json_body)."""
    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    filename = f"{base}-results.json"

    result_array = []
    for u in utterances:
        result = u.evaluation_result
        is_error = bool(result and result.error_status in _ERROR_STATUSES) or result is None
        contract = result.normalized_contract if result else None
        response_text = None
        if contract:
            response_text = (contract.get("chatbotResponse") or {}).get("normalizedText")
        scores = (result.evaluation_scores or []) if result else []
        parameters = []
        if not is_error:
            for s in scores:
                if not isinstance(s, dict):
                    continue
                entry: dict = {
                    "parameter_name": s.get("parameter_name", ""),
                    "score": s.get("score"),
                    "reasoning": s.get("reasoning") or "",
                }
                if "verdict" in s:
                    entry["verdict"] = s["verdict"]
                parameters.append(entry)

        sources = _extract_sources(contract)
        result_array.append({
            "utteranceText": u.utterance_text,
            "testId": u.test_id,
            "utteranceIntent": result.utterance_intent if result else None,
            "chatbotResponse": response_text,
            "overallVerdict": result.evaluation_verdict if result else None,
            "errorStatus": result.error_status if result else None,
            "errorStage": result.error_stage if result else None,
            "parameters": parameters,
            "sources": [
                {"url": s["url"], "title": s["title"], "chunk": s["chunk"],
                 "scope": s["scope"], "documentId": s["documentId"]}
                for s in sources
            ],
        })

    return filename, json.dumps(result_array, indent=2, ensure_ascii=False)


_DICT_S1 = [
    ("Column", "Type", "Description", "Allowed values"),
    ("User Question", "Text", "The user question sent to the chatbot", "Any UTF-8 string"),
    ("Test Case Reference", "Text", "Reference ID from the uploaded CSV", "Any string"),
    ("Intent Category", "Text", "Intent category from the evaluator", "Evaluator-defined or blank"),
    ("Chatbot Answer", "Text", "The chatbot's plain-text reply", "Any string"),
    ("Overall Result", "Text", "Worst-case verdict for this utterance", "pass / warn / fail / blank"),
    ("Dimension", "Text", "The scoring dimension being evaluated", "Evaluator-defined"),
    ("Score (0–1)", "Decimal", "Numeric score for this dimension", "0.0 (worst) to 1.0 (best)"),
    ("Result", "Text", "Verdict for this dimension", "pass / warn / fail / blank"),
    ("Justification", "Text", "Evaluator's rationale for this score", "Any string"),
    ("Source #", "Integer", "1-based position of the KB source for this row; blank when no sources retrieved", "1, 2, 3, … or blank"),
    ("Source Title", "Text", "KB article or document title", "Any string or blank"),
    ("Source URL", "Text", "Direct URL to the KB article", "URL or blank"),
    ("Document ID", "Text", "Stable document identifier", "Any string or blank"),
    ("Scope", "Text", "Collection or namespace this article belongs to", "Any string or blank"),
    ("Retrieved Text", "Text", "Full text passage retrieved as grounding context", "Any string or blank"),
]

_DICT_VERDICTS = [
    ("Verdict value", "Meaning"),
    ("pass", "Score meets or exceeds the configured threshold for this dimension"),
    ("warn", "Score is below threshold but above the minimum acceptable floor — review recommended"),
    ("fail", "Score is below the minimum acceptable floor — action required"),
    ("(blank)", "Utterance errored before evaluation; no score was produced"),
]

_DICT_S2 = [
    ("Column", "Type", "Description"),
    ("Row ID", "Text", "Internal ID — joins to Sheet 1 rows for this utterance"),
    ("Test Case Reference", "Text", "Reference ID from the uploaded CSV (repeated for readability)"),
    ("User Question", "Text", "The user question (repeated for readability)"),
    ("Source #", "Integer", "1-based position of this source in the retrieved list"),
    ("Source Title", "Text", "KB article or document title"),
    ("Source URL", "Text", "Direct URL to the KB article"),
    ("Document ID", "Text", "Stable document identifier"),
    ("Scope", "Text", "Collection or namespace this article belongs to"),
    ("Retrieved Text", "Text", "Full text passage retrieved as grounding context"),
]


def _write_data_dictionary(ws) -> None:
    def _section(title: str) -> None:
        c = WriteOnlyCell(ws, value=title)
        c.font = _SECTION_FONT
        ws.append([c])

    _section("Sheet 1 — Results: Column Definitions")
    ws.append([])
    for row in _DICT_S1:
        _write_header_row(ws, row, fill=True) if row[0] == "Column" else ws.append(list(row))

    ws.append([])
    _section("Verdict Value Definitions")
    ws.append([])
    for row in _DICT_VERDICTS:
        _write_header_row(ws, row, fill=True) if row[0] == "Verdict value" else ws.append(list(row))

    ws.append([])
    _section("Sheet 2 — Retrieved Sources: Column Definitions")
    ws.append([])
    for row in _DICT_S2:
        _write_header_row(ws, row, fill=True) if row[0] == "Column" else ws.append(list(row))


def results_xlsx_builder(job: Job, utterances: list) -> tuple[str, bytes]:
    """Three-sheet XLSX (write-only): Results / Retrieved Sources / Data Dictionary.

    Uses openpyxl write_only=True so rows are streamed to the ZIP buffer without
    ever holding cell objects in RAM — safe for large jobs (2000+ utterances).
    """
    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    filename = f"{base}-results.xlsx"

    wb = openpyxl.Workbook(write_only=True)

    # ── Sheet 1: Results ──────────────────────────────────────────────────────
    ws1 = wb.create_sheet("Results")
    _set_ws_widths(ws1, [40, 15, 20, 40, 15, 20, 10, 12, 40, 12, 30, 40, 20, 15, 60])
    _write_header_row(ws1, [_friendly(c) for c in (
        "utteranceText", "testId", "utteranceIntent", "chatbotResponse", "overallVerdict",
        "parameterName", "score", "verdict", "reasoning",
        "sourceIndex", "title", "url", "documentId", "scope", "chunk",
    )])

    # ── Sheet 2: Retrieved Sources ────────────────────────────────────────────
    ws2 = wb.create_sheet("Retrieved Sources")
    _set_ws_widths(ws2, [20, 15, 40, 12, 30, 40, 20, 15, 60])
    _write_header_row(ws2, [_friendly(c) for c in (
        "utteranceId", "testId", "utteranceText",
        "sourceIndex", "title", "url", "documentId", "scope", "chunk",
    )])

    for row in _long_format_rows(utterances):
        ws1.append(row)

    for u in utterances:
        result = u.evaluation_result
        contract = result.normalized_contract if result else None
        for idx, src in enumerate(_extract_sources(contract), start=1):
            ws2.append([
                str(u.utterance_id), u.test_id or "", u.utterance_text,
                idx, src["title"], src["url"], src["documentId"], src["scope"], src["chunk"],
            ])

    # ── Sheet 3: Data Dictionary ──────────────────────────────────────────────
    ws3 = wb.create_sheet("Data Dictionary")
    _set_ws_widths(ws3, [35, 15, 65, 40])
    _write_data_dictionary(ws3)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return filename, buf.read()


def _flat_schema(utterances: list) -> tuple[list[str], int, list[list[dict]]]:
    """Pass 1: collect ordered unique dimension names, max source count, and per-utterance sources.

    Returns (dim_names, max_sources, sources_cache) so flat builders avoid a
    second call to _extract_sources per utterance.
    """
    dim_names: list[str] = []
    max_sources = 0
    sources_cache: list[list[dict]] = []
    for u in utterances:
        result = u.evaluation_result
        scores = (result.evaluation_scores or []) if result else []
        for s in scores:
            if isinstance(s, dict):
                name = s.get("parameter_name") or ""
                if name and name not in dim_names:
                    dim_names.append(name)
        contract = result.normalized_contract if result else None
        srcs = _extract_sources(contract)
        sources_cache.append(srcs)
        if len(srcs) > max_sources:
            max_sources = len(srcs)
    return dim_names, max_sources, sources_cache


def _flat_row(
    u,
    dim_names: list[str],
    max_sources: int,
    sources: list[dict],
) -> list:
    """Build a single flat row for one utterance. sources must be pre-extracted."""
    result = u.evaluation_result
    contract = result.normalized_contract if result else None
    response_text = ""
    if contract:
        response_text = (contract.get("chatbotResponse") or {}).get("normalizedText") or ""
    overall_verdict = (result.evaluation_verdict if result else None) or ""
    intent = (result.utterance_intent if result else None) or ""

    scores_by_dim: dict = {}
    for s in ((result.evaluation_scores or []) if result else []):
        if isinstance(s, dict):
            name = s.get("parameter_name") or ""
            if name:
                scores_by_dim[name] = s

    row: list = [u.utterance_text, u.test_id or "", intent, response_text, overall_verdict]

    for name in dim_names:
        s = scores_by_dim.get(name, {})
        row.extend([s.get("score", ""), s.get("verdict") or "", s.get("reasoning", "")])

    for i in range(max_sources):
        if i < len(sources):
            src = sources[i]
            row.extend([src["title"], src["url"], src["documentId"], src["scope"], src["chunk"]])
        else:
            row.extend(["", "", "", "", ""])

    return row


def _flat_header(dim_names: list[str], max_sources: int) -> list[str]:
    fixed = ["utteranceText", "testId", "utteranceIntent", "chatbotResponse", "overallVerdict"]
    dim_cols = []
    for name in dim_names:
        dim_cols.extend([f"{name}_score", f"{name}_verdict", f"{name}_reasoning"])
    src_cols = []
    for i in range(1, max_sources + 1):
        src_cols.extend([
            f"source{i}_title", f"source{i}_url", f"source{i}_documentId",
            f"source{i}_scope", f"source{i}_chunk",
        ])
    return [_friendly(c) for c in fixed + dim_cols + src_cols]


def results_flat_csv_builder(job: Job, utterances: list) -> tuple[str, str]:
    """One-row-per-utterance CSV with dynamic dimension and source columns (BL-002)."""
    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    filename = f"{base}-results-flat.csv"

    dim_names, max_sources, sources_cache = _flat_schema(utterances)
    header = _flat_header(dim_names, max_sources)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for u, sources in zip(utterances, sources_cache):
        writer.writerow(_flat_row(u, dim_names, max_sources, sources))
    return filename, buf.getvalue()


_FLAT_DICT_FIXED = [
    ("Column", "Type", "Description"),
    ("User Question", "Text", "The user question sent to the chatbot"),
    ("Test Case Reference", "Text", "Reference ID from the uploaded CSV"),
    ("Intent Category", "Text", "Intent category from the evaluator"),
    ("Chatbot Answer", "Text", "The chatbot's plain-text reply"),
    ("Overall Result", "Text", "Worst-case verdict across all dimensions (pass / warn / fail)"),
]

_FLAT_DICT_DIMS = [
    ("Pattern", "Type", "Description"),
    ("{name}: Score (0–1)", "Decimal", "Numeric score for the named dimension (0.0 worst — 1.0 best)"),
    ("{name}: Result", "Text", "Verdict for the named dimension (pass / warn / fail / blank)"),
    ("{name}: Justification", "Text", "Evaluator rationale for the named dimension score"),
]

_FLAT_DICT_SRCS = [
    ("Pattern", "Type", "Description"),
    ("Source {N}: Title", "Text", "KB article or document title for source N"),
    ("Source {N}: URL", "Text", "Direct URL to the KB article for source N"),
    ("Source {N}: Document ID", "Text", "Stable document identifier for source N"),
    ("Source {N}: Scope", "Text", "Collection or namespace for source N"),
    ("Source {N}: Retrieved Text", "Text", "Full text passage retrieved as grounding context for source N"),
]


def results_flat_xlsx_builder(job: Job, utterances: list) -> tuple[str, bytes]:
    """Two-sheet flat XLSX (write-only): Results (Flat) / Data Dictionary (BL-002)."""
    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    filename = f"{base}-results-flat.xlsx"

    dim_names, max_sources, sources_cache = _flat_schema(utterances)
    header = _flat_header(dim_names, max_sources)

    wb = openpyxl.Workbook(write_only=True)

    # ── Sheet 1: Results (Flat) ───────────────────────────────────────────────
    ws1 = wb.create_sheet("Results (Flat)")
    fixed_widths = [40, 15, 20, 40, 15]
    dim_widths = [10, 12, 40] * len(dim_names)
    src_widths = [30, 40, 20, 15, 60] * max_sources
    _set_ws_widths(ws1, fixed_widths + dim_widths + src_widths)
    _write_header_row(ws1, header)
    for u, sources in zip(utterances, sources_cache):
        ws1.append(_flat_row(u, dim_names, max_sources, sources))

    # ── Sheet 2: Data Dictionary ──────────────────────────────────────────────
    ws2 = wb.create_sheet("Data Dictionary")
    _set_ws_widths(ws2, [30, 15, 65])

    def _section(title: str) -> None:
        c = WriteOnlyCell(ws2, value=title)
        c.font = _SECTION_FONT
        ws2.append([c])

    _section("Fixed Columns")
    ws2.append([])
    for row in _FLAT_DICT_FIXED:
        _write_header_row(ws2, row, fill=True) if row[0] == "Column" else ws2.append(list(row))

    ws2.append([])
    _section("Dimension Columns  —  one group per evaluated parameter: {name}_score / {name}_verdict / {name}_reasoning")
    ws2.append([])
    for row in _FLAT_DICT_DIMS:
        _write_header_row(ws2, row, fill=True) if row[0] == "Pattern" else ws2.append(list(row))

    ws2.append([])
    _section("Source Columns  —  one group per retrieved KB source: source{N}_title / source{N}_url / …")
    ws2.append([])
    for row in _FLAT_DICT_SRCS:
        _write_header_row(ws2, row, fill=True) if row[0] == "Pattern" else ws2.append(list(row))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return filename, buf.read()


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
