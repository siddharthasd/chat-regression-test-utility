# Phase 0 Research: CSV Upload & Validation Service (Module 8)

**Date**: 2026-06-04 | **Plan**: `specs/011-csv-upload-validation/plan.md`

Built on `foundation`. Stdlib-only; no new deps. Resolves the plan-level decisions.

---

## R1: Decode + BOM handling (FR-004)
**Decision**: Read raw bytes; if they start with `codecs.BOM_UTF8` (`b"\xef\xbb\xbf"`), slice it off; then `bytes.decode("utf-8")`. On `UnicodeDecodeError`, return an `encoding` error naming the failing byte offset (`exc.start`).
**Rationale**: explicit BOM strip is deterministic (FR-004 requires silent strip + no warning); decoding the whole buffer up front means the rest of the pipeline works on `str`. Files are bounded by the size gate (R6) so full-buffer decode is safe.
**Alternatives**: `utf-8-sig` codec (strips BOM but masks the "is it really UTF-8" check less clearly) — we strip manually for an explicit offset on failure.

## R2: RFC-4180 parsing + delimiter guard (FR-005)
**Decision**: `csv.reader(io.StringIO(text))` with default dialect (comma, `"`-quoting) — preserves quoted embedded newlines/commas losslessly (FR-005, SC-008). Before parsing, a light **delimiter guard**: if the first line contains no `,` but does contain `;` or `\t`, reject with `unsupported_delimiter`.
**Rationale**: stdlib `csv` is RFC-4180-correct; full delimiter sniffing (`csv.Sniffer`) is unreliable and out of scope (v1 = comma only). The guard catches the obvious semicolon/tab mistake without false-positiving single-column comma files.
**Alternatives**: `csv.Sniffer` (flaky on short/edge inputs) — rejected.

## R3: Conditional-password switch (FR-006, reshape)
**Decision**: Read `expects = bool(job.connector_expects_per_row_password)` from the **Draft Job snapshot** (009 column), not the live registry (parent FR-023). When `True`: `password` is a required header + non-empty per row, staged into the store. When `False`/unset: `password` is optional — if present it's preserved as `extra_metadata`, if absent the upload still proceeds; store is **not** populated for this job's rows.
**Rationale**: the reshape made password-ness a per-connector property; the snapshot is the single source of truth. None/unset → False is defensive (upload can run before connector selection in degenerate flows; the wizard normally sets it).

## R4: DB↔store atomicity ordering (FR-018, SC-010)
**Decision**: Phase the work — (1) validate+parse with **zero side effects**, (2) commit DB writes in one `get_session()` txn (the commit point), (3) mutate the in-memory store **only after** the DB commit returns. Capture created `utterance_id`s inside the txn for the store keys.
**Rationale**: the store isn't a transactional resource, so true 2-phase commit is impossible. Ordering side effects (validate → DB commit → store) means any failure rolls the DB back via `get_session` and leaves the store at its pre-upload state. Store `put`/`clear_job` are pure dict ops that don't fail.

## R5: Replace-on-upload (FR-018a, SC-011)
**Decision**: Inside the same persist txn, `UtteranceRepository.delete_by_job(job_id)` first (cascade removes prior rows + their EvaluationResults per 009 FR-010), then `bulk_create` the new rows, then `set_csv_metadata`. Post-commit, `password_store.clear_job(job_id)` precedes staging the new entries.
**Rationale**: 009's `delete_by_job` is draft-guarded and cascades; doing it in the same txn as the new insert makes replace atomic (FR-018a). The store clear is part of the post-commit stage step so old credentials never coexist with new.

## R6: Size gate before read (FR-002, SC-003)
**Decision**: After confirming the path exists/readable, `os.path.getsize(path)` and compare to `max_bytes` **before** opening for read. Exceed → `size_exceeded` naming limit + actual. `max_bytes` = call arg, else `HARNESS_MAX_UPLOAD_BYTES` env, else 50 MiB.
**Rationale**: `stat`-based size check reads no content (SC-003: "no file-content loaded beyond metadata"). A configurable knob with a sensible default satisfies FR-002.

## R7: Error model + per-row collection (FR-020, US2)
**Decision**: One `UploadResult` with `success: bool` + `errors: list[ErrorEntry]`. `ErrorEntry(category: ErrorCategory, row: int | None, column: str | None, message: str)`. Categories: `job_not_found`, `job_not_draft`, `file_not_accessible`, `file_not_readable`, `size_exceeded`, `encoding`, `unsupported_delimiter`, `missing_column`, `duplicate_column`, `no_data_rows`, `row_column_mismatch`, `empty_value`. Row-level checks (mismatch/empty) **collect all offenders** before returning; structural checks (encoding/header) short-circuit. Validation failure never raises — it returns `success=False`.
**Rationale**: the wizard (003) needs a structured, per-row report to render inline (FR-020); returning rather than raising keeps the caller simple. Short-circuiting structural errors avoids nonsense row errors on a file that couldn't even be parsed.

## R8: Store handoff shape (FR-015)
**Decision**: 011 calls `harness.password_store.put(job_id, utterance_id, password)` / `.clear_job(job_id)` — the module built in 012. 011 is the producer, 012 the consumer; per-row eviction + Job-terminal backstop + process-exit clear all live on the consumer/store side (012 FR-011, already implemented).
**Rationale**: the store already exists with the exact `(job_id, utterance_id) → password` shape FR-015 prescribes; 011 only needs the producer calls. Single source of truth, no duplication.

---

*All decisions resolved. Implementation can proceed.*
