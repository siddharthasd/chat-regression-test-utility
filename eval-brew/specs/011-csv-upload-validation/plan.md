# Implementation Plan: CSV Upload & Validation Service (Module 8)

**Branch**: `011-csv-upload-validation` | **Date**: 2026-06-04 | **Spec**: `specs/011-csv-upload-validation/spec.md`
**Base**: `foundation` (010+009+006+007+008+013+014+012, tip `a0859b9`, 286 passed / 7 xfailed / ruff clean)

## Summary

Module 8 is the **producer** of `Utterance` rows and the **producer** of the in-memory password store that the orchestrator (012) consumes. It takes a CSV file destined for a `draft` Job, validates it (UTF-8/BOM, RFC-4180, required columns, non-empty cells, size gate, draft-status gate), parses it, persists one `Utterance` per data row via 009's `UtteranceRepository`, records `Job.sourceCSVFilename` + `Job.totalUtteranceCount`, and stages each row's `password` into `harness.password_store` — **but only when the Draft Job's snapshotted connector has `expectsPerRowPassword == true`**. Passwords are never persisted (FR-014). Upload is atomic and replace-on-re-upload (FR-018/018a).

This module is **pure service layer** — the spec states it is invoked exclusively by the wizard's Step 2 (`003 FR-005`) and has *no separate CLI/API surface in v1*. So 011 ships a callable Python API (`process_upload(...)`) + result types; the Flask wizard UI is 003's job. (Same pattern as 012 introducing `password_store` ahead of its 011 producer.)

## Technical Context

**Language**: Python 3.11+ (3.13 in CI). **Storage**: SQLite via 009 (`UtteranceRepository`, `JobRepository`, `get_session`). **Stdlib only** for parsing: `csv`, `codecs`, `io`, `pathlib`, `os`, `uuid` (via 009). **No new dependencies.** **Testing**: pytest + per-test `engine.init_db(tmp)` isolation; `harness.password_store._reset_for_tests()`. **Lint**: ruff (line-length 100).

**Reuse (no duplication)**:
- 009 `UtteranceRepository.bulk_create` (generates UUID `utterance_id`, accepts 1-based `row_index`, `extra_metadata`), `UtteranceRepository.delete_by_job` (replace), `JobRepository.set_csv_metadata` (sets `source_csv_filename` + `total_utterance_count`, draft-guarded), `JobRepository.get`, `get_session` (atomic txn).
- 009 `Job.connector_expects_per_row_password` snapshot column (set by `set_connector_snapshot`) — the conditional-password switch (FR-006).
- `harness.password_store` (built in 012): `put` / `clear_job` — the producer calls these (consumer is 012).
- 009 immutability: `bulk_create`/`delete_by_job`/`set_csv_metadata` already refuse a non-draft parent → that *is* the FR-003 commit-time re-check (raises `UtteranceImmutableError`/`SnapshotImmutableError`).

## Source layout (new)

```
src/harness/csv_upload/__init__.py     # re-exports process_upload, UploadResult, ErrorEntry, ErrorCategory
src/harness/csv_upload/parser.py       # decode (UTF-8/BOM), RFC-4180 parse, header+row structural validation
src/harness/csv_upload/result.py       # UploadResult / ErrorEntry / ErrorCategory dataclasses+enum (FR-019/020)
src/harness/csv_upload/service.py      # process_upload(...) orchestration: validate→parse→persist→stage store
tests/unit/csv_upload/__init__.py
tests/unit/csv_upload/test_parser.py
tests/integration/test_csv_upload.py
```

No edits to existing modules. No package-data (no templates).

## Public API (contract — see contracts/service-api.md)

```python
process_upload(
    job_id: str,
    file_path: str | Path,
    *,
    filename: str | None = None,      # defaults to basename(file_path)
    max_bytes: int | None = None,     # defaults to HARNESS_MAX_UPLOAD_BYTES or 50 MiB
) -> UploadResult
```
`UploadResult`: `success: bool`, `utterances_created: int`, `distinct_test_ids: int`, `warnings: list[str]`, `errors: list[ErrorEntry]`. `ErrorEntry`: `category: ErrorCategory`, `row: int | None`, `column: str | None`, `message: str`. Never raises for *validation* failure — returns `success=False` + populated `errors` (FR-020). Bad job / non-draft / file IO surface as `errors` too, not exceptions, so the wizard can render them.

## Processing pipeline (service.py)

1. **Job gate** (FR-001/003): `JobRepository.get(job_id)`; missing → `job_not_found`; status != draft → `job_not_draft` (names current status). Read `expects = bool(job.connector_expects_per_row_password)` from the snapshot (None/unset → False, password optional — defensive; the wizard sets the connector by commit time).
2. **File gate** (FR-001/002): path exists/readable → else `file_not_accessible`/`file_not_readable`; `os.path.getsize` > `max_bytes` → `size_exceeded` (names limit + actual) **before any read**.
3. **Decode** (FR-004): read bytes, strip leading UTF-8 BOM, `bytes.decode("utf-8")`; `UnicodeDecodeError` → `encoding` (names the bad-byte position).
4. **Delimiter guard** (FR-005): if the header line has no comma but contains `;`/`\t` → `unsupported_delimiter`.
5. **Parse** (FR-005): `csv.reader` (RFC-4180; preserves quoted embedded newlines/commas).
6. **Header validation** (FR-006/007): trim each header name; duplicate → `duplicate_column`; require `utteranceText`,`testId` (+`password` when `expects`); missing → `missing_column` (one entry per missing). Position-independent.
7. **Row validation** (FR-009/010/011): skip entirely-blank rows (count → warning); each non-blank row: column-count == header → else `row_column_mismatch`; required cells non-empty (whitespace-only == empty) → else `empty_value` (one entry per offending row+column). **Collect all row errors** before returning (actionable per-row report). Zero data rows → `no_data_rows`.
8. **Persist atomically** (FR-013/016/017/018/018a): single `get_session()` txn → `UtteranceRepository.delete_by_job(job_id)` (replace, no-op if none) → `bulk_create` (rows in order; `extra_metadata` = non-required columns dict, or None) → `set_csv_metadata(job_id, basename, n)`. Capture the created `utterance_id`s (in order) inside the txn.
9. **Stage store** (FR-015/018a): **after** commit, `password_store.clear_job(job_id)` always (replace + defensive); if `expects`, `password_store.put(job_id, utterance_id, password)` for each row (zip created ids with parsed passwords, same order). DB commit precedes store mutation, so a failed commit never leaks store entries (FR-010/SC-010); store ops can't fail.
10. **Summary** (FR-019): `success=True`, `utterances_created=n`, `distinct_test_ids=len({testId})`, `warnings`.

## Atomicity note (DB ↔ in-memory store)

True two-resource atomicity is impossible (the store isn't transactional), so the design orders side effects to make failure safe: **all validation/parsing happens with zero side effects**; the **DB commit is the commit point**; the **store is mutated only after the DB commit succeeds**. A failure before/at commit → DB rolled back by `get_session`, store untouched (still pre-upload state) → satisfies FR-018/SC-010. Replace (FR-018a) clears old store entries as part of the post-commit stage step.

## Configuration

`HARNESS_MAX_UPLOAD_BYTES` env var (int bytes); default **50 MiB** (`50 * 1024 * 1024`), matching the parent's 1,000-row design target plus payload headroom. Overridable per-call via `max_bytes`.

## Constitution Check

No constitution constraints beyond the harness premises (single-user, no auth, in-memory-only passwords). Module honors `010 Q2` (passwords never persisted, CSV file not retained — only basename). No new deps. Gate: **PASS** (pre- and post-design).

## Phase 0 / 1 outputs
- `research.md` — R1–R8 (decode/BOM, RFC-4180 + delimiter guard, conditional-password switch, atomicity ordering, replace-on-upload, size-gate-before-read, error model, store handoff).
- `data-model.md` — entity flows (transient parse result → Utterance rows + store), field mapping, validation rules.
- `contracts/service-api.md` — `process_upload` + `UploadResult`/`ErrorEntry`/`ErrorCategory`.
- `quickstart.md` — fixtures + service-call walkthrough.
- CLAUDE.md SPECKIT marker → `specs/011-csv-upload-validation/plan.md`.
