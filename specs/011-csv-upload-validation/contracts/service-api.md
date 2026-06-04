# Contract: CSV Upload Service Public API (Module 8)

**Date**: 2026-06-04
Consumer: the wizard's Step 2 (`003 FR-005`, not yet built). Produces 009 `Utterance` rows + the `harness.password_store` entries that 012 consumes.

---

## `harness.csv_upload`

### `process_upload(job_id, file_path, *, filename=None, max_bytes=None) -> UploadResult`

| Param | Type | Meaning |
|---|---|---|
| `job_id` | `str` | target Draft Job |
| `file_path` | `str \| Path` | local path to the CSV (size-checked before read) |
| `filename` | `str \| None` | display name; defaults to `basename(file_path)` → stored as `Job.source_csv_filename` |
| `max_bytes` | `int \| None` | size limit; defaults to `HARNESS_MAX_UPLOAD_BYTES` env, else 50 MiB |

**Behavior**: validate (job/draft/size/encoding/delimiter/header/rows) → on any failure return `UploadResult(success=False, errors=[...])` with **no** DB or store mutation. On success: atomically replace-or-create `Utterance` rows, set `Job.total_utterance_count` + `Job.source_csv_filename`, stage passwords into the store (iff the snapshot's `connector_expects_per_row_password`), and return `UploadResult(success=True, ...)`. **Never raises for validation failure**; bad job / non-draft / file IO are returned as `errors`, not exceptions. Idempotent in effect: a second call replaces the first's rows + store entries (FR-018a).

### `UploadResult` (frozen dataclass)
```python
success: bool
utterances_created: int          # 0 on failure
distinct_test_ids: int           # count of distinct testId (FR-019c), 0 on failure
warnings: list[str]              # e.g. "skipped 2 blank trailing row(s)"
errors: list[ErrorEntry]         # empty on success
```

### `ErrorEntry` (frozen dataclass)
```python
category: ErrorCategory
row: int | None                  # 1-based source row, when applicable
column: str | None               # offending column name, when applicable
message: str                     # human-readable
```

### `ErrorCategory` (StrEnum)
`job_not_found` · `job_not_draft` · `file_not_accessible` · `file_not_readable` · `size_exceeded` · `encoding` · `unsupported_delimiter` · `missing_column` · `duplicate_column` · `no_data_rows` · `row_column_mismatch` · `empty_value`

---

## Guarantees
- **Atomic** (FR-018/SC-010): validation/parse have no side effects; DB writes commit together in one `get_session()`; store mutated only post-commit.
- **No password persistence** (FR-014/SC-005): `password` never reaches the DB; only `harness.password_store` (in-memory) when `expects_per_row_password`.
- **Lossless** (SC-008): `utterance_text` round-trips byte-equal (UTF-8, embedded newlines, Unicode).
- **Replace** (FR-018a/SC-011): re-upload to a draft job atomically replaces prior rows + store entries.

## Configuration
`HARNESS_MAX_UPLOAD_BYTES` (int bytes, default `52428800` = 50 MiB).
