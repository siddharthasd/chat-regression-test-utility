"""Decode + RFC-4180 parse + structural validation — the no-side-effect core (FR-004..011).

Everything here operates on bytes/str and returns data; nothing touches the DB or
the password store. `service.process_upload` drives this, then persists.
"""

from __future__ import annotations

import codecs
import csv
import io
from dataclasses import dataclass, field

from harness.csv_upload.result import ErrorCategory, ErrorEntry

REQUIRED_ALWAYS = ("utteranceText", "testId")
PASSWORD_COLUMN = "password"


@dataclass
class ParsedRow:
    """One validated data row. `password` is None when the column is absent."""

    utterance_text: str
    test_id: str
    source_row: int  # 1-based data-row index
    password: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedUpload:
    """Outcome of parse+validate: rows on success, or a populated `errors` list."""

    rows: list[ParsedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[ErrorEntry] = field(default_factory=list)


def decode_csv(raw: bytes) -> tuple[str | None, ErrorEntry | None]:
    """Strip a leading UTF-8 BOM and decode as UTF-8 (FR-004).

    Returns ``(text, None)`` on success or ``(None, ErrorEntry)`` for invalid UTF-8.
    """
    if raw.startswith(codecs.BOM_UTF8):
        raw = raw[len(codecs.BOM_UTF8):]
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, ErrorEntry(
            category=ErrorCategory.ENCODING,
            message=f"file is not valid UTF-8 (invalid byte at offset {exc.start})",
        )


def _is_blank(row: list[str]) -> bool:
    return all((cell or "").strip() == "" for cell in row)


def parse_and_validate(text: str, *, require_password: bool) -> ParsedUpload:
    """Parse comma-delimited CSV and validate header + rows (FR-005..011)."""
    result = ParsedUpload()

    # Delimiter guard (R2): a header with no comma but a ';'/tab is the common mistake.
    first_line = text.splitlines()[0] if text.strip() else ""
    if "," not in first_line and (";" in first_line or "\t" in first_line):
        result.errors.append(
            ErrorEntry(
                category=ErrorCategory.UNSUPPORTED_DELIMITER,
                message="only comma-delimited CSV is supported (detected ';' or tab)",
            )
        )
        return result

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        result.errors.append(
            ErrorEntry(category=ErrorCategory.NO_DATA_ROWS, message="file is empty")
        )
        return result

    names = [h.strip() for h in header]

    # Duplicate headers (FR-006).
    seen: set[str] = set()
    dups = sorted({n for n in names if n in seen or seen.add(n)})
    if dups:
        result.errors.append(
            ErrorEntry(
                category=ErrorCategory.DUPLICATE_COLUMN,
                message=f"duplicate header column(s): {', '.join(dups)}",
            )
        )

    required = list(REQUIRED_ALWAYS) + ([PASSWORD_COLUMN] if require_password else [])
    missing = [c for c in required if c not in names]
    for col in missing:
        result.errors.append(
            ErrorEntry(
                category=ErrorCategory.MISSING_COLUMN,
                message=f"missing required column: {col}",
                column=col,
            )
        )

    if result.errors:  # header is structurally broken — don't emit nonsense row errors
        return result

    idx = {name: i for i, name in enumerate(names)}
    extra_cols = [n for n in names if n not in REQUIRED_ALWAYS and n != PASSWORD_COLUMN]
    has_password_col = PASSWORD_COLUMN in idx

    data_row_number = 0
    skipped_blank = 0
    for raw_row in reader:
        if _is_blank(raw_row):
            skipped_blank += 1
            continue
        data_row_number += 1

        if len(raw_row) != len(names):
            result.errors.append(
                ErrorEntry(
                    category=ErrorCategory.ROW_COLUMN_MISMATCH,
                    message=(
                        f"row {data_row_number} has {len(raw_row)} columns, "
                        f"expected {len(names)}"
                    ),
                    row=data_row_number,
                )
            )
            continue

        # Non-empty required cells (FR-009; whitespace counts as empty).
        row_ok = True
        for col in required:
            if (raw_row[idx[col]] or "").strip() == "":
                row_ok = False
                result.errors.append(
                    ErrorEntry(
                        category=ErrorCategory.EMPTY_VALUE,
                        message=f"row {data_row_number}: required column '{col}' is empty",
                        row=data_row_number,
                        column=col,
                    )
                )
        if not row_ok:
            continue

        result.rows.append(
            ParsedRow(
                utterance_text=raw_row[idx["utteranceText"]],
                test_id=raw_row[idx["testId"]],
                source_row=data_row_number,
                password=raw_row[idx[PASSWORD_COLUMN]] if has_password_col else None,
                extra={c: raw_row[idx[c]] for c in extra_cols},
            )
        )

    if skipped_blank:
        result.warnings.append(f"skipped {skipped_blank} blank trailing row(s)")

    if not result.errors and data_row_number == 0:
        result.errors.append(
            ErrorEntry(
                category=ErrorCategory.NO_DATA_ROWS,
                message="no data rows found (header only)",
            )
        )

    return result
