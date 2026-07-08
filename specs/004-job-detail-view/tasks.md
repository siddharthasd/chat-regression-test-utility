---
description: "Task list for Job Detail & Traceability View (Module 13)"
---

# Tasks: Job Detail & Traceability View (Module 13)

**Input**: Design documents from `specs/004-job-detail-view/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R9) ✅, data-model.md ✅, contracts/ui-routes.md ✅, quickstart.md ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `004-job-detail-view` on `foundation` (006-014 + 003 + 002). **Server-rendered Flask + thin polling JS.** Owns `GET /jobs/<id>/detail` (the dashboard's row-click target). Reuses 009 `JobRepository` (`get`/`transition_to_cancelling`/`delete`), `UtteranceRepository.get_by_job_ordered` (+ the `Utterance.evaluation_result` one-to-one), `enums`, `dashboard.view.format_timestamp`, and the `credential`/`password` secret-subfield convention. **No new deps.** Snapshot is the source of truth (registries not read). Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1/US2/US4/US5/US6 on story phases (US3 was removed in v1); Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [X] T001 Create scaffold: `src/harness/ui/detail/__init__.py` (exports `bp`), `src/harness/ui/detail/routes.py` (empty `bp = Blueprint("detail", __name__, template_folder="templates")`), `src/harness/ui/detail/view.py` (empty), `src/harness/ui/detail/templates/detail/` (dir).
- [X] T002 Register the detail blueprint in `src/harness/ui/__init__.py::create_app()`; add `"harness.ui.detail" = ["templates/detail/*.html"]` to `[tool.setuptools.package-data]`; `python -m pip install -e ".[dev]"`.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T003 Implement `src/harness/ui/detail/view.py`: `mask_descriptor(d)` (credential/password → `••••••••`, keep mode/headerName/username, never decrypt — FR-005); `metadata_view(job)` (all FR-003 fields, masked descriptors, status_label/badge, hybrid timestamps via `dashboard.view.format_timestamp`, job-level counts); `row_view(utterance, declared_dims)` (FR-007/008 fields + `scores_cells` ordered by declared dims then unexpected, awaiting/— placeholders, `has_unexpected_dims`, expand artifacts, never `password`); `apply_filters(rows, verdicts, error_only, test_ids, q)` (AND; q over utterance+response only); `sort_rows(rows, sort, dir)` (any col except scores; verdict fail>warn>pass; default row_index asc); `reconstruct_csv(job, utterances) -> (filename, text)` (no password; -reconstructed/-partial + marker).

**Checkpoint**: pure projection/masking/filter/CSV layer unit-usable; blueprint mounts.

---

## Phase 3: User Story 1 — Metadata panel for one job (Priority: P1) 🎯 MVP

- [X] T004 [US1] `routes.py`: `GET /jobs/<id>/detail` (load job → `metadata_view` + rows; 404 unknown) rendering `detail/index.html`'s metadata panel; `GET /jobs/<id>/download.csv` (`reconstruct_csv` → `text/csv` attachment). `index.html` created with the panel (masked config, declared dims, counts, status badge, download link) + tester-identity chrome. **NOTE**: `GET /jobs/<id>/download.csv` and `reconstruct_csv()` are REMOVED by feature 018. Do not implement this route when 018 is in scope.
- [X] T005 [US1] `tests/integration/test_detail_ui.py`: panel renders persisted config; a secret (bearer token / basic password) is **masked and never in the HTML** (SC-003); counts match; `draft` job shows blank started/completed; `download.csv` contains the utterances, omits `password`, and is marked reconstructed (partial for non-terminal) (SC-009). Per-test `engine.init_db(tmp)`. **NOTE**: SC-009 (`download.csv`) test is superseded by 018's results-download tests. Remove or skip this test case when implementing 018.

**Checkpoint**: MVP — the panel answers "what is this job?" with secrets masked.

---

## Phase 4: User Story 2 — Inspect one utterance's full trace (Priority: P1)

- [X] T006 [US2] Extend `index.html` with the Results Table (one row per utterance: rowIndex, testId, utterance/response truncated, verdict badge, ordered scores cells, error status, unexpected-dim indicator) + per-row expand revealing full input (no password), raw response, normalized contract, evaluation result, harness_annotations, and error_status/stage/details — each large JSON in `<pre>` with a copy button (FR-007/008/009).
- [X] T007 [US2] `test_detail_ui.py`: completed row expand shows all four artifacts; a `failed` row shows its 9-value `error_stage` + details + the partial upstream artifact (e.g. `connector_normalization` → raw present, contract null); scores render in declared-dimension order; an unexpected-dimension row shows the indicator (SC-002).

**Checkpoint**: One-click full traceability per row.

---

## Phase 5: User Story 4 — Sort, filter, search the table (Priority: P2)

- [X] T008 [US4] `routes.py` (same file): read `verdict` (multi), `error_only`, `test_id` (multi), `q`, `sort`, `dir` → `apply_filters` + `sort_rows`; `index.html` adds verdict/error/testId filter controls, a search box, sortable headers (NO sort on Scores), and the "Visible: N of M" indicator (FR-011/012/013/014/014a).
- [X] T009 [US4] `test_detail_ui.py`: verdict filter, error-only toggle, testId filter, utterance/response search, and their AND-combination; sort toggles; search does NOT match raw-JSON-only content; "Visible: N of M" appears when filtered (SC-010).

**Checkpoint**: The table is sliceable; scores stay unsortable.

---

## Phase 6: User Story 5 — Live incremental population (Priority: P2)

- [X] T010 [US5] `routes.py` (same file): `GET /jobs/<id>/detail.json` → `{status, status_label, badge_class, total, processed, failed, row_count, terminal}`, `404` if deleted; add the inline poller to `index.html` (3 s; patch panel; reload on row_count growth; redirect to `/` on 404; stop at terminal) (FR-015/016/020).
- [X] T011 [US5] `test_detail_ui.py`: `detail.json` returns live counts + `terminal` flags (running false, completed/failed/cancelled true); deleting the job → `detail.json` 404 (FR-020 path) (SC-004).

**Checkpoint**: Non-terminal jobs update without manual refresh; deleted-elsewhere handled.

---

## Phase 7: User Story 6 — Cancel / Delete from the detail view (Priority: P2)

- [X] T012 [US6] `routes.py` (same file): `POST /jobs/<id>/cancel` (iff queued/running → `transition_to_cancelling`; `InvalidTransitionError` → 409) + `POST /jobs/<id>/delete` (iff draft/failed/cancelled, re-checked → `delete` cascade → redirect to dashboard); `index.html` shows Cancel iff queued/running and Delete iff draft/failed/cancelled, each with a confirm prompt (FR-018/019).
- [X] T013 [US6] `test_detail_ui.py`: Cancel control present exactly for queued/running and absent otherwise (SC-006); Delete present exactly for draft/failed/cancelled (SC-007); cancel transitions to `cancelling`; delete removes the job + rows and redirects to `/` (SC-008); cancel on an already-terminal job → 409.

**Checkpoint**: The canonical job-level actions are correctly gated.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T014 [P] `python -m ruff check src tests --fix`; resolve findings (line-length 100).
- [X] T015 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 338 tests still pass + adequate `ui/detail/` coverage; check whether the credential-masking XFAIL `test_no_password_column_in_detail_view` now XPASSes and, if so, un-xfail it.
- [X] T016 [P] Execute `specs/004-job-detail-view/quickstart.md`; verify FR→File + SC matrices; confirm `CLAUDE.md` marker → `004` plan.

---

## Dependencies & Execution Order

- **Setup** (T001–T002) → no deps. **Foundational** (T003) → projection/masking/filter/CSV block the stories.
- **US1 (P3)** → detail route + panel + download (MVP). **US2** → results table + expand in the same `index.html`. **US4** → query-param slicing. **US5** → detail.json + poller. **US6** → cancel/delete.
- `routes.py` and `index.html` are each one file grown across US1/US2/US4/US5/US6 → those tasks are **sequential**; `test_detail_ui.py` is extended per story → sequential within.

### Critical path
Setup → Foundational → US1 → US2 → US4 → US5 → US6 → Polish.

### Parallel opportunities
- T014/T016 [P] once tests pass. The single routes/template/test files are otherwise sequential.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: the panel renders one job's config with secrets masked + a password-free reconstructed CSV (SC-003/009).

### Incremental delivery
US1 → US2 → US4 → US5 → US6 → Polish.

---

## Notes

- **This module flips the credential-masking XFAILs** that gate on the detail surface — `mask_descriptor` + autoescape + the password-free CSV are exactly what they assert (verify in T015).
- The Job snapshot is the source of truth — registries (013/014) are never read; archived registrations render the snapshot as-is.
- Evaluator-emitted data (scores `reasoning`, raw response) is rendered via Jinja autoescape, never `|safe` (FR-007a XSS-safe).
- Reuse `dashboard.view.format_timestamp`; replicate the tiny badge/label logic locally (dashboard's are private) to avoid cross-blueprint coupling.
- Live updates are polling; `detail.json` is the tested surface, the reload-on-growth script a progressive enhancement. UI tests use the per-test `engine.init_db(tmp)` recipe. Commit after each task/group.
