"""CSV Upload & Validation Service (Module 8).

Validates + parses a CSV destined for a draft Job, persists one `Utterance` per row
via 009, and stages per-row passwords into `harness.password_store` (the producer
side; the orchestrator 012 is the consumer). Passwords are never persisted::

    from harness.csv_upload import process_upload
    result = process_upload(job_id, "regression.csv")
    if not result.success:
        for e in result.errors: ...
"""

from __future__ import annotations

from harness.csv_upload.result import ErrorCategory, ErrorEntry, UploadResult
from harness.csv_upload.service import process_upload

__all__ = ["ErrorCategory", "ErrorEntry", "UploadResult", "process_upload"]
