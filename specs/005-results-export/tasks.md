---
description: "Task list for Results Export Service (Module 14)"
---

# Tasks: Results Export Service (Module 14)

**Input**: Design documents from `specs/005-results-export/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R8) ✅, data-model.md ✅, contracts/export-api.md ✅, quickstart.md ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `005-results-export` on `foundation` (006-014 + 003 + 002 + 004). **The final module.** A reusable builder (`harness.export`) + a streaming route (`harness.ui.export_ui`) + a Download Results control added to 004's detail page. Reuses 009 reads (`JobRepository`/`UtteranceRepository` + `Utterance.evaluation_result` one-to-one) and `harness.ui.detail.view.mask_descriptor`. Stdlib `csv`/`json`/`zipfile` only — **no new deps.** Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US4 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [ ] T001 Create scaffold: `src/harness/export/__init__.py` (exports `build_export`, `FORMATS`), `src/harness/export/builder.py` (empty), `src/harness/ui/export_ui/__init__.py` (exports `bp`), `src/harness/ui/export_ui/routes.py` (empty `bp = Blueprint("export", __name__)`), `tests/unit/export/__init__.py`.
- [ ] T002 Register the export blueprint in `src/harness/ui/__init__.py::create_app()`. (No package-data — export_ui ships no templates; the control lives in 004's `detail/index.html`.)

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T003 Implement `src/harness/export/builder.py`: `FORMATS=("csv","json","zip")`; `job_metadata(job, exported_at)` (FR-005, masked descriptors via `detail.view.mask_descriptor`, `partial`); `row_record(utterance, declared_dims)` (FR-006 fields, scores ordered by declared dims then unexpected — FR-006a, **no password / no userFeedback / no top-level reasoning**); `build_json` (`{job,rows,partial}`, nested native + `_unparseable` fallback — FR-009); `build_csv` (rectangular repeated metadata columns + per-row columns, nested fields `json.dumps`-ed per cell — FR-007/008); `build_zip` (csv+json via `zipfile` — FR-002); `build_export(job, utterances, fmt, *, exported_at=None) -> (filename, mimetype, body)` (filename `<slug>-results[-partial].<ext>`).

**Checkpoint**: builder unit-testable without Flask.

---

## Phase 3: User Story 1 — Export a completed job in CSV / JSON / zip (Priority: P1) 🎯 MVP

- [ ] T004 [US1] `src/harness/ui/export_ui/routes.py`: `GET /jobs/<id>/export?format=` (load job → 404 if gone, 400 if draft/queued or 0 rows, else `build_export` → streaming `Response` with `Content-Disposition`). Edit `detail/routes.py` to pass `can_export = row_count>0 and status not in {draft,queued}` (both render paths); add the Download Results control (format `<select>` + button → `export.export`) to `detail/index.html` when `can_export`.
- [ ] T005 [P] [US1] `tests/unit/export/test_builder.py`: CSV is rectangular w/ repeated metadata + JSON-stringified nesteds (parse a cell back); JSON is `{job,rows,partial}` valid (SC-010); zip holds both; credentials masked + **no password / no token plaintext** anywhere (SC-005); scores ordered by declared dims then unexpected (FR-006a).
- [ ] T006 [US1] `tests/integration/test_export_ui.py`: a completed job → download CSV, JSON, zip (correct `Content-Type`/`Content-Disposition`, every row once — SC-001/003); rendered detail page shows the Download Results control with all three options. Per-test `engine.init_db(tmp)`.

**Checkpoint**: MVP — a completed job exports in all three formats, secrets safe.

---

## Phase 4: User Story 2 — Partial export of a running job (Priority: P2)

- [ ] T007 [US2] `tests/integration/test_export_ui.py` (same file): a `running` job with K rows → export has exactly K rows, filename contains `partial`, and the inline marker is present (CSV `partial` column true / JSON `partial: true`) (SC-007); `cancelling` behaves the same.

**Checkpoint**: Non-terminal exports are partial-annotated snapshots.

---

## Phase 5: User Story 3 — Re-export reflects latest persisted state (Priority: P2)

- [ ] T008 [US3] `tests/integration/test_export_ui.py` (same file): export a job, persist more rows, re-export → the second file contains the new rows; assert no caching (fresh build each click) (SC-006, FR-003/012).

**Checkpoint**: Every click regenerates from current state.

---

## Phase 6: User Story 4 — Failed/cancelled triage export + gating (Priority: P3)

- [ ] T009 [US4] `tests/integration/test_export_ui.py` (same file): a `failed` job export includes every persisted row with `errorStatus`/`errorStage`/`errorDetails` intact; a `cancelled` job likewise; `draft`/`queued` (no rows) → the control is absent on the detail page AND `GET …/export` returns 400 (SC-008); a deleted job id → 404 (SC-011, FR-014).

**Checkpoint**: Triage exports complete; gating + race handled.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T010 [P] `python -m ruff check src tests --fix`; resolve findings (line-length 100).
- [ ] T011 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 356 tests still pass + adequate `export`/`export_ui` coverage.
- [ ] T012 [P] Execute `specs/005-results-export/quickstart.md`; verify FR→File + SC matrices; confirm `CLAUDE.md` marker → `005` plan.

---

## Dependencies & Execution Order

- **Setup** (T001–T002) → no deps. **Foundational** (T003) → the builder blocks all stories.
- **US1 (P3)** → route + detail control (MVP). **US2/US3/US4** → tests over behavior already built in T003/T004 (partial flag, fresh build, gating) — `test_export_ui.py` is extended per story → sequential within.
- `detail/routes.py` + `detail/index.html` are edited once (T004).

### Critical path
Setup → Foundational → US1 → US2 → US3 → US4 → Polish.

### Parallel opportunities
- T005 (`test_builder.py`) is [P] vs the integration file. T010/T012 [P] once tests pass.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: a completed job downloads as CSV/JSON/zip with secrets masked and no password (SC-001/003/005).

### Incremental delivery
US1 → US2 → US3 → US4 → Polish.

---

## Notes

- **This is the export side of the credential-masking contract**: passwords are omitted entirely (key absent), credentials masked via the shared `mask_descriptor`, never decrypted (FR-006/011, SC-005).
- CSV stays rectangular (FR-007) — the partial signal is a column, never a comment line (reconciles FR-010 with FR-007); contrast 004's source-CSV download which keeps its comment marker.
- Scores order follows the snapshotted declared dimensions so cross-job exports concatenate trivially (FR-006a).
- The export ignores the detail view's filters/search — always all persisted rows (FR-016).
- UI tests use the per-test `engine.init_db(tmp)` recipe. Commit after each task/group.
