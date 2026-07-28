"""Result + error types returned by the CSV upload service (FR-019/020)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ErrorCategory(StrEnum):
    """Closed set of upload-failure categories (data-model.md §3)."""

    JOB_NOT_FOUND = "job_not_found"
    JOB_NOT_DRAFT = "job_not_draft"
    FILE_NOT_ACCESSIBLE = "file_not_accessible"
    FILE_NOT_READABLE = "file_not_readable"
    SIZE_EXCEEDED = "size_exceeded"
    ENCODING = "encoding"
    UNSUPPORTED_DELIMITER = "unsupported_delimiter"
    MISSING_COLUMN = "missing_column"
    DUPLICATE_COLUMN = "duplicate_column"
    NO_DATA_ROWS = "no_data_rows"
    ROW_COLUMN_MISMATCH = "row_column_mismatch"
    EMPTY_VALUE = "empty_value"


@dataclass(frozen=True)
class ErrorEntry:
    """One actionable validation error (FR-020). `row` is 1-based when applicable."""

    category: ErrorCategory
    message: str
    row: int | None = None
    column: str | None = None


@dataclass(frozen=True)
class UploadResult:
    """Summary of an upload attempt (FR-019 on success, FR-020 on failure)."""

    success: bool
    utterances_created: int = 0
    distinct_test_ids: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[ErrorEntry] = field(default_factory=list)
