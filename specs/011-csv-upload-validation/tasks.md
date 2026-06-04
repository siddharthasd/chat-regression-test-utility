---
description: "Task list for CSV Upload & Validation Service (Module 8)"
---

# Tasks: CSV Upload & Validation Service (Module 8)

**Input**: Design documents from `specs/011-csv-upload-validation/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R8) ✅, data-model.md ✅, contracts/service-api.md ✅, quickstart.md ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `011-csv-upload-validation` on `foundation` (010+009+006+007+008+013+014+012). **Pure service layer — no Flask UI** (the wizard 003 owns that; spec: no separate CLI/API in v1). Reuses 009 `UtteranceRepository` (`bulk_create`/`delete_by_job`), `JobRepository` (`get`/`set_csv_metadata`), `get_session`, the `Job.connector_expects_per_row_password` snapshot column, and `harness.password_store` (`put`/`clear_job`, built in 012). **Stdlib-only parsing; no new deps.** Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US5 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [ ] T001 Create scaffold: `src/harness/csv_upload/__init__.py`, `src/harness/csv_upload/result.py` (empty), `src/harness/csv_upload/parser.py` (empty), `src/harness/csv_upload/service.py` (empty), `tests/unit/csv_upload/__init__.py`. (No package-data: no templates.)

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T002 [P] Implement `src/harness/csv_upload/result.py`: `ErrorCategory(StrEnum)` (12 values per data-model.md §3), `ErrorEntry` (frozen: `category`/`row`/`column`/`message`), `UploadResult` (frozen: `success`/`utterances_created`/`distinct_test_ids`/`warnings`/`errors`) (FR-019/020).
- [ ] T003 Implement `src/harness/csv_upload/parser.py` — the no-side-effect decode+parse+validate core: `decode_csv(raw: bytes) -> str` (strip UTF-8 BOM, decode, raise/return `encoding` on `UnicodeDecodeError` naming the byte offset, R1); delimiter guard (R2); `parse_and_validate(text, *, require_password: bool) -> ParsedUpload` returning `(rows: list[ParsedRow], warnings, errors)` where `ParsedRow` has `utterance_text`/`test_id`/`password`/`extra: dict`/`source_row`. Header validation (trim names, dup → `duplicate_column`, required `utteranceText`/`testId` [+`password` if `require_password`] → `missing_column`); row validation (blank-row skip→warning, col-count → `row_column_mismatch`, non-empty required → `empty_value`; collect all offenders); `no_data_rows` (FR-004/005/006/007/009/010/011).

**Checkpoint**: result types + parser unit-testable in isolation (no DB).

---

## Phase 3: User Story 1 — Upload a valid CSV end-to-end (Priority: P1) 🎯 MVP

- [ ] T004 [US1] Implement `src/harness/csv_upload/service.py::process_upload(job_id, file_path, *, filename=None, max_bytes=None) -> UploadResult`: job gate (`JobRepository.get` → `job_not_found`/`job_not_draft`, read `expects = bool(job.connector_expects_per_row_password)`); file gate (`os.path.exists`/readable + `os.path.getsize` vs `max_bytes`/`HARNESS_MAX_UPLOAD_BYTES`/50 MiB → `size_exceeded`, **before read**); `decode_csv` + `parse_and_validate(require_password=expects)`; on any errors return `UploadResult(success=False, errors=...)`; else one `get_session()` txn → `delete_by_job` → `bulk_create` (order preserved, `extra_metadata` from extras or None) → `set_csv_metadata(basename, n)`, capturing created `utterance_id`s; post-commit `password_store.clear_job` + (if `expects`) `put` per row; return success summary (distinct testId count + warnings). Re-export `process_upload`, `UploadResult`, `ErrorEntry`, `ErrorCategory` from `__init__.py` (FR-001/002/003/013/015/016/017/018/019).
- [ ] T005 [P] [US1] `tests/unit/csv_upload/test_parser.py`: valid header+rows parse (order, byte-equal text); extra columns → `extra` dict; distinct-testId helper; `require_password` toggles the `password` requirement.
- [ ] T006 [US1] `tests/integration/test_csv_upload.py`: happy path for `expects_per_row_password=true` (5 rows, header `utteranceText,testId,password`) → success summary (5 created, 0 warnings), 5 Utterances `rowIndex` 1–5 with fresh UUIDs, `total_utterance_count==5`, `source_csv_filename==basename`, passwords in `password_store` but **zero password bytes in the DB file** (SC-001/005/006/009); and `expects=false` with no `password` column → same (a)–(c) + store unpopulated for the job.

**Checkpoint**: MVP — a valid CSV creates Utterance rows + (conditionally) stages passwords.

---

## Phase 4: User Story 2 — Reject malformed CSV with per-row errors (Priority: P1)

- [ ] T007 [P] [US2] `tests/unit/csv_upload/test_parser.py` (same file): `missing_column` (names each), `duplicate_column`, `empty_value` (one entry per offending row+column, whitespace==empty, 1-based), `row_column_mismatch` (expected vs observed), `no_data_rows` (header-only), `encoding` (invalid UTF-8), `unsupported_delimiter` (semicolon/tab) (FR-004/005/006/009/010, SC-002).
- [ ] T008 [US2] `tests/integration/test_csv_upload.py` (same file): the three US2 cases (wrong encoding, missing `password` column, empty `testId` in row 3) each → `success=False` with the right category, AND the Utterance table empty + `total_utterance_count`/`source_csv_filename` unmutated + store unpopulated (SC-002, FR-018 no-partial-state).

**Checkpoint**: Malformed uploads are rejected with actionable per-row detail; nothing persists.

---

## Phase 5: User Story 3 — Reject upload when Job not in `draft` (Priority: P2)

- [ ] T009 [US3] `tests/integration/test_csv_upload.py` (same file): a valid CSV against a Job in each of the six non-draft statuses → `job_not_draft` naming the status, no rows persisted, Job unmutated (SC-004); plus the commit-time guard — 009's `bulk_create`/`set_csv_metadata` raise on a non-draft parent, so a job flipped out of draft mid-upload rolls back atomically (US3 scenario 2, FR-003). Service catches that and returns `job_not_draft`.

**Checkpoint**: Non-draft uploads are refused at entry and at commit.

---

## Phase 6: User Story 4 — Reject upload exceeding max file size (Priority: P2)

- [ ] T010 [US4] `tests/integration/test_csv_upload.py` (same file): `max_bytes=1024` + a larger CSV → `size_exceeded` naming limit + actual; no rows persisted, Job unmutated; under-limit proceeds (SC-003, FR-002). Confirm the size check reads no content (path-size based).

**Checkpoint**: Oversized uploads rejected before content read.

---

## Phase 7: User Story 5 — Encoding & parsing edge cases (Priority: P2)

- [ ] T011 [P] [US5] `tests/unit/csv_upload/test_parser.py` (same file): UTF-8 BOM silently stripped (no warning); quoted embedded-newline value preserved; trailing blank rows skipped → `warnings` names the count (not an error); non-comma column order accepted; whitespace-trimmed header names match (FR-004/005/007/011, SC-007/008).
- [ ] T012 [US5] `tests/integration/test_csv_upload.py` (same file): one fixture exercising BOM + quoted multi-line `utteranceText` + 2 trailing blank rows + emoji/Unicode → utterances persisted byte-equal (lossless round-trip from the DB), blank-row count in `warnings`, count excludes blanks (SC-007/008).

**Checkpoint**: Real-world CSV warts handled without data loss.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T013 [P] `tests/integration/test_csv_upload.py` (same file): replace-on-upload — upload `A.csv` (N_A rows + store entries when `expects`), then `B.csv` to the same draft job → exactly N_B rows + N_B store entries, zero `A.csv` traces in DB or store (SC-010/011, FR-018a); and an injected commit failure leaves DB + store at pre-upload state (atomicity).
- [ ] T014 [P] `python -m ruff check src tests --fix`; resolve findings (line-length 100, datetime/UP).
- [ ] T015 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 286 tests still pass + adequate `csv_upload/` coverage.
- [ ] T016 [P] Execute `specs/011-csv-upload-validation/quickstart.md`; verify FR→File + SC matrices; confirm `CLAUDE.md` marker → `011` plan.

---

## Dependencies & Execution Order

- **Setup** (T001) → no deps. **Foundational** (T002–T003) → block all stories (result types + parser).
- **US1 (P3)** → `service.py` (T004) wires parser + persistence + store; the MVP.
- **US2 (P4)** → tests over T003's error paths + T004's "return errors, persist nothing".
- **US3 (P5)**, **US4 (P6)** → tests over T004's job-gate + size-gate (built in T004).
- **US5 (P7)** → tests over T003's decode/parse edge handling.
- **Polish** → after the stories.

### Critical path
Setup → Foundational (T002 ‖ then T003) → US1 (T004) → US2 → US3 → US4 → US5 → Polish. `service.py` is built once (T004) with all gates; stories US3/US4 only *test* it. `parser.py` (T003) built once; US2/US5 test its branches. `test_csv_upload.py` is one file extended per story → sequential within.

### Parallel opportunities
- T002 ‖ (then) T003. `test_parser.py` tasks (T005 ‖ T007 ‖ T011) are [P] among themselves but share one file → in practice append sequentially; the integration file is sequential across stories.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: a valid CSV creates the right Utterance rows, sets the Job counters, stages passwords in-memory, and persists zero password bytes (SC-001/005).

### Incremental delivery
US1 → US2 → US3 → US4 → US5 → Polish.

---

## Notes

- 011 is the **producer**; 012 is the **consumer** of `harness.password_store`. Per-row eviction / Job-terminal backstop / process-exit clear all live on the 012/store side (already implemented) — 011 only calls `put`/`clear_job`.
- Passwords NEVER touch the DB (FR-014): there is no Utterance password column; the only password sink is the in-memory store, only when `connector_expects_per_row_password`.
- Atomicity is achieved by ordering: validate/parse (no side effects) → DB commit (commit point) → store mutation (post-commit). A pre-commit failure leaves both DB and store untouched.
- Tests use the per-test `engine.init_db(tmp)` isolation recipe + `password_store._reset_for_tests()`. Commit after each task/group.
