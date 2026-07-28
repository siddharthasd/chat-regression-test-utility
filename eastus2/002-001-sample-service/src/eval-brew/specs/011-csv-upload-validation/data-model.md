# Phase 1 Data Model: CSV Upload & Validation Service (Module 8)

**Date**: 2026-06-04 | **Plan**: `specs/011-csv-upload-validation/plan.md`

011 owns **no persistent entity** — it produces 009's `Utterance` rows + Job-counter updates and stages the in-memory password store. This documents the transient structures + mappings.

---

## 1. Persistent writes (009 entities)

| Entity / field | Source | Repo call |
|---|---|---|
| `Utterance.utterance_id` | generated UUID (009) | `UtteranceRepository.bulk_create` |
| `Utterance.job_id` | upload target | `bulk_create(job_id, ...)` |
| `Utterance.utterance_text` | row `utteranceText` (byte-equal) | `bulk_create` |
| `Utterance.test_id` | row `testId` | `bulk_create` |
| `Utterance.row_index` | 1-based data-row index | `bulk_create` |
| `Utterance.extra_metadata` | non-required columns → `dict` (or `None`) | `bulk_create` |
| `Job.total_utterance_count` | count of valid data rows | `JobRepository.set_csv_metadata` |
| `Job.source_csv_filename` | `basename(file)` | `JobRepository.set_csv_metadata` |

`password` is **never** written (FR-014) — no Utterance column for it.

## 2. In-memory write (012's store)

| Key | Value | When | Call |
|---|---|---|---|
| `(job_id, utterance_id)` | row `password` | only if `expects_per_row_password` | `password_store.put` |
| (all for job) | — cleared — | always, post-commit (replace + defensive) | `password_store.clear_job` |

## 3. Transient structures

- **ParsedRow** (in-memory): `{utteranceText, testId, password?, extra: dict}` + source row number (1-based). Lives for one upload; `password` migrates to the store, the rest to `Utterance`.
- **UploadResult** (returned): `success: bool`, `utterances_created: int`, `distinct_test_ids: int`, `warnings: list[str]`, `errors: list[ErrorEntry]`.
- **ErrorEntry**: `category: ErrorCategory`, `row: int | None`, `column: str | None`, `message: str`.
- **ErrorCategory** (enum): `job_not_found`, `job_not_draft`, `file_not_accessible`, `file_not_readable`, `size_exceeded`, `encoding`, `unsupported_delimiter`, `missing_column`, `duplicate_column`, `no_data_rows`, `row_column_mismatch`, `empty_value`.

## 4. Required columns (conditional)

| Column | Required? |
|---|---|
| `utteranceText` | always |
| `testId` | always |
| `password` | iff Job snapshot `connector_expects_per_row_password == true` |

Header names trimmed before comparison; case-sensitive; position-independent; duplicates rejected.

## 5. Validation rules → requirement

| Rule | FR | Category on failure |
|---|---|---|
| job exists | FR-001 | `job_not_found` |
| job is draft (entry + commit-time via 009 guard) | FR-003 | `job_not_draft` |
| size ≤ max (before read) | FR-002 | `size_exceeded` |
| valid UTF-8 (BOM stripped) | FR-004 | `encoding` |
| comma-delimited | FR-005 | `unsupported_delimiter` |
| required columns present | FR-006 | `missing_column` |
| no duplicate headers | FR-006 | `duplicate_column` |
| ≥1 data row | edge | `no_data_rows` |
| row col-count == header | FR-010 | `row_column_mismatch` |
| required cells non-empty (whitespace==empty) | FR-009 | `empty_value` |
| blank trailing rows skipped (warning, not error) | FR-011 | — (warning) |

## 6. Atomicity / lifecycle

```
validate + parse (no side effects)
        │  any failure → return success=False, errors=[...]; DB + store untouched
        ▼
one get_session() txn:  delete_by_job → bulk_create → set_csv_metadata   ← commit point
        │  txn failure (e.g., job left draft) → rolled back; store untouched (FR-018/SC-010)
        ▼
post-commit: password_store.clear_job(job_id); if expects: put(...) per row   (FR-015/018a)
        ▼
return success=True summary
```

Replace-on-upload (FR-018a): the `delete_by_job` + new `bulk_create` share one txn; old store entries cleared in the post-commit step before new ones staged.
