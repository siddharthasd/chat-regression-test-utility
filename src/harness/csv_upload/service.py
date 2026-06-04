"""process_upload — validate → parse → persist → stage the in-memory store (FR-001..018a).

The producer of 009 `Utterance` rows and of the `harness.password_store` entries the
orchestrator (012) consumes. Atomicity is by ordering: validation/parse have no side
effects; the DB commit is the commit point; the store is mutated only after commit.
"""

from __future__ import annotations

import os
from pathlib import Path

from harness import password_store
from harness.csv_upload.parser import decode_csv, parse_and_validate
from harness.csv_upload.result import ErrorCategory, ErrorEntry, UploadResult
from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.exceptions import SnapshotImmutableError, UtteranceImmutableError
from harness.persistence.repositories import JobRepository, UtteranceRepository
from harness.persistence.repositories.types import UtteranceCreateData

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB (FR-002)


def _max_bytes(explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    env = os.environ.get("HARNESS_MAX_UPLOAD_BYTES")
    return int(env) if env else DEFAULT_MAX_BYTES


def _fail(*errors: ErrorEntry) -> UploadResult:
    return UploadResult(success=False, errors=list(errors))


def process_upload(
    job_id: str,
    file_path: str | Path,
    *,
    filename: str | None = None,
    max_bytes: int | None = None,
) -> UploadResult:
    """Validate + persist a CSV upload for a draft Job. Never raises for validation
    failure — returns ``UploadResult(success=False, errors=[...])`` instead."""
    path = Path(file_path)
    display_name = filename or path.name

    # 1. Job gate (FR-001/003) — read the conditional-password flag from the snapshot.
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None:
            return _fail(ErrorEntry(ErrorCategory.JOB_NOT_FOUND, f"job not found: {job_id}"))
        if job.status != JobStatus.DRAFT:
            return _fail(
                ErrorEntry(
                    ErrorCategory.JOB_NOT_DRAFT,
                    f"job is '{job.status}', not 'draft'; upload is only allowed for draft jobs",
                )
            )
        expects = bool(job.connector_expects_per_row_password)

    # 2. File + size gate (FR-001/002) — size checked before any content read.
    if not path.exists():
        return _fail(ErrorEntry(ErrorCategory.FILE_NOT_ACCESSIBLE, f"file not found: {path}"))
    if not os.access(path, os.R_OK):
        return _fail(ErrorEntry(ErrorCategory.FILE_NOT_READABLE, f"file not readable: {path}"))
    limit = _max_bytes(max_bytes)
    size = path.stat().st_size
    if size > limit:
        return _fail(
            ErrorEntry(
                ErrorCategory.SIZE_EXCEEDED,
                f"file size {size} bytes exceeds the configured limit of {limit} bytes",
            )
        )

    # 3. Decode (FR-004).
    text, enc_error = decode_csv(path.read_bytes())
    if enc_error is not None:
        return _fail(enc_error)

    # 4. Parse + structural/row validation (FR-005..011) — no side effects yet.
    parsed = parse_and_validate(text, require_password=expects)
    if parsed.errors:
        return UploadResult(success=False, warnings=parsed.warnings, errors=parsed.errors)

    rows = parsed.rows

    # 5. Persist atomically (FR-013/016/017/018/018a). The DB commit is the commit point.
    try:
        with get_session() as session:
            utt_repo = UtteranceRepository(session)
            utt_repo.delete_by_job(job_id)  # replace-on-upload (no-op if none)
            create_data: list[UtteranceCreateData] = [
                {
                    "utterance_text": r.utterance_text,
                    "test_id": r.test_id,
                    "row_index": r.source_row,
                    "extra_metadata": r.extra or None,
                }
                for r in rows
            ]
            created = utt_repo.bulk_create(job_id, create_data)
            utterance_ids = [u.utterance_id for u in created]
            JobRepository(session).set_csv_metadata(job_id, display_name, len(rows))
    except (UtteranceImmutableError, SnapshotImmutableError):
        # The job left `draft` between the entry gate and commit (US3 scenario 2) — the
        # 009 layer refused the write and rolled back. Surface it; store untouched.
        return _fail(
            ErrorEntry(
                ErrorCategory.JOB_NOT_DRAFT,
                "job is no longer in 'draft' status; upload was rolled back",
            )
        )

    # 6. Stage the in-memory store AFTER the DB commit (FR-015/018a).
    password_store.clear_job(job_id)  # always: replace + defensive
    if expects:
        for utterance_id, row in zip(utterance_ids, rows, strict=True):
            password_store.put(job_id, utterance_id, row.password)

    return UploadResult(
        success=True,
        utterances_created=len(rows),
        distinct_test_ids=len({r.test_id for r in rows}),
        warnings=parsed.warnings,
    )
