---
description: "Task list for Dashboard & Job Listing (Module 12)"
---

# Tasks: Dashboard & Job Listing (Module 12)

**Input**: Design documents from `specs/002-dashboard-job-listing/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R8) ✅, data-model.md ✅, contracts/ui-routes.md ✅, quickstart.md ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `002-dashboard-job-listing` on `foundation` (006-014 + 003). **Server-rendered Flask + thin polling JS.** Reuses 009 `JobRepository` (+ one new `list_all()`), `delete`/`delete_all_failed_and_cancelled`, `JobStatus`/`TERMINAL_STATUSES`, 003 `wizard.new_job`, the existing standalone-HTML template style + per-test `engine.init_db(tmp)` isolation. **No new deps.** Row data is read straight from `Job` columns (no Utterance aggregation). Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US5 on story phases; Setup/Foundational/Cleanup/Polish carry no label.

---

## Phase 1: Setup

- [X] T001 Create scaffold: `src/harness/ui/dashboard/__init__.py` (exports `bp`), `src/harness/ui/dashboard/routes.py` (empty `bp = Blueprint("dashboard", __name__, template_folder="templates")`), `src/harness/ui/dashboard/view.py` (empty), `src/harness/ui/dashboard/templates/dashboard/` (dir).
- [X] T002 Register the dashboard blueprint in `src/harness/ui/__init__.py::create_app()`; add `"harness.ui.dashboard" = ["templates/dashboard/*.html"]` to `[tool.setuptools.package-data]`; `python -m pip install -e ".[dev]"`.
- [X] T003 [P] Add `list_all(self) -> list[Job]` (ordered `created_at` desc) to `src/harness/persistence/repositories/job.py` (FR-002/009a).

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 Implement `src/harness/ui/dashboard/view.py`: `row_view(job, now)` (all FR-003 fields + derived `status_label`/`badge_class`/`deletable`/`terminal`, "Completed with errors" when `completed and failed>0`), `format_timestamp(dt, now) -> (display, title)` (relative <24h else absolute, FR-003a), `apply_filters(rows, statuses, connectors, created_bys, q)` (AND, FR-006/007/008), `sort_rows(rows, sort, direction)` (underlying value, default created_at desc, FR-009/009a), `distinct_facets(jobs)` (FR-006).

**Checkpoint**: pure projection/filter/sort layer unit-usable; blueprint mounts (empty).

---

## Phase 3: User Story 1 — See every job at a glance (Priority: P1) 🎯 MVP

- [X] T005 [US1] `routes.py`: `GET /` → `JobRepository.list_all()` → `row_view` per job → render `dashboard/index.html` (single table, color-coded badges per status, all FR-003 columns in canonical order, hybrid timestamps, no-jobs empty state with the Create-New-Job CTA). `index.html` created here (header w/ tester identity; table; empty state).
- [X] T006 [US1] `tests/integration/test_dashboard_ui.py`: seed jobs across ≥4 statuses → `GET /` lists all with distinguishable badges (FR-004, SC-005); a `completed`+`failed>0` job shows "Completed with errors" while a clean completed does not (FR-005, SC-006); empty DB → no-jobs empty state + Create-New-Job CTA (FR-014). Per-test `engine.init_db(tmp)` isolation.

**Checkpoint**: MVP — the root page lists every job with status badges + empty state.

---

## Phase 4: User Story 2 — Start a new job from the dashboard (Priority: P2)

- [X] T007 [US2] Add the "Create New Job" control to `index.html` (→ `url_for('wizard.new_job')`), present + prominent in BOTH populated and empty states; `test_dashboard_ui.py` asserts the link is present in both states (FR-011, SC-008).

**Checkpoint**: One-click entry into the wizard from any dashboard state.

---

## Phase 5: User Story 3 — Drill into a job's detail (Priority: P2)

- [X] T008 [US3] In `index.html`, make each row body link to `/jobs/<id>/detail` (literal href — 004's future route; the dashboard does only the handoff); ensure any in-row control (delete) is a nested form so it doesn't trigger the row link. `test_dashboard_ui.py`: row carries the `/jobs/<id>/detail` href + `data-job-id` (FR-010).

**Checkpoint**: Clean navigation handoff to the (future) detail view.

---

## Phase 6: User Story 4 — Filter, sort, search (Priority: P3)

- [X] T009 [US4] `routes.py` (same file): read `status`/`connector`/`created_by` (repeatable), `q`, `sort`, `dir` query params → `apply_filters` + `sort_rows`; `index.html` renders filter controls from `distinct_facets`, a search box, sortable column headers w/ active indicator, and the no-matches empty state + clear-filters link (FR-006/007/008/009/015).
- [X] T010 [US4] `test_dashboard_ui.py`: status/connector/created_by filters in isolation + combination + name search AND-combine (FR-008); sort toggles asc/desc by underlying value (FR-009); zero-match → no-matches state distinct from no-jobs (FR-015, SC-003/004).

**Checkpoint**: The list is filterable/sortable/searchable, server-side.

---

## Phase 7: User Story 5 — Near-real-time updates (Priority: P3)

- [X] T011 [US5] `routes.py` (same file): `GET /dashboard/jobs.json` → `{"jobs":[{job_id,status,status_label,processed,total,failed,terminal}...]}`; add the inline polling script to `index.html` (3 s `fetch`, patch rows by `data-job-id`, stop when all rendered rows terminal) (FR-012/013).
- [X] T012 [US5] `test_dashboard_ui.py`: `jobs.json` returns live counters + `terminal` flags for seeded jobs (running non-terminal, completed/failed/cancelled terminal) (SC-002/007).

**Checkpoint**: Non-terminal rows update without reload; polling stops at terminal.

---

## Phase 8: Dashboard cleanup actions (FR-010b/c)

- [X] T013 `routes.py` (same file): `POST /dashboard/jobs/<id>/delete` (re-read in txn; delete only if status ∈ {failed, cancelled} else 409; cascade via `JobRepository.delete`) + `POST /dashboard/clear-terminal` (`delete_all_failed_and_cancelled`); `index.html` shows a delete button ONLY on failed/cancelled rows (nested form + confirm) and a top-level "Clear all failed and cancelled" control with the exact count, disabled at 0 (FR-010b/c).
- [X] T014 `test_dashboard_ui.py`: delete on a failed/cancelled job removes it; delete on a completed/running job → 409 + still present (FR-010b); delete control absent on non-failed/cancelled rows; clear-terminal removes exactly the failed+cancelled set and reports the count (FR-010c, SC-009).

**Checkpoint**: Surgical + bulk cleanup of terminal-error jobs, correctly gated.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T015 [P] `python -m ruff check src tests --fix`; resolve findings (line-length 100).
- [X] T016 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 323 tests still pass + adequate `ui/dashboard/` coverage.
- [X] T017 [P] Execute `specs/002-dashboard-job-listing/quickstart.md`; verify FR→File + SC matrices; confirm `CLAUDE.md` marker → `002` plan.

---

## Dependencies & Execution Order

- **Setup** (T001–T003) → no deps (T003 [P]). **Foundational** (T004) → projection/filter/sort blocks the stories.
- **US1 (P3)** → `GET /` + `index.html` (MVP). **US2/US3** → small additions to `index.html`. **US4** → query-param filtering in `routes.py` + controls in `index.html`. **US5** → `jobs.json` + polling script. **Cleanup** → delete/clear routes + controls.
- `routes.py` and `index.html` are each one file grown across US1/US4/US5/Cleanup → those tasks are **sequential**; `test_dashboard_ui.py` is extended per story → sequential within.

### Critical path
Setup → Foundational → US1 → US2 → US3 → US4 → US5 → Cleanup → Polish.

### Parallel opportunities
- T003 [P] (distinct file). T015/T017 [P] once tests pass. The single routes/template/test files are otherwise sequential.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: the root page lists every job with status badges, the completed-with-errors distinction, and the empty state (SC-001/005/006).

### Incremental delivery
US1 → US2 → US3 → US4 → US5 → Cleanup → Polish.

---

## Notes

- Row data is a pure projection of `Job` columns — `processed_count`/`failed_count` are maintained by the orchestrator, `total_utterance_count` by 011. No Utterance aggregation.
- The detail-view drill-in is a literal `/jobs/<id>/detail` href (NOT `url_for`, which would `BuildError` on 004's unregistered endpoint) — the honest handoff stub 004 will satisfy.
- Live updates are polling-based (no new deps); `jobs.json` is the tested surface, the inline script a progressive enhancement. SC-002 (≤5 s) and SC-007 (stop at terminal) are the observable contract.
- Dashboard delete is narrower than 009's `delete` (which also allows `draft`): the route gates to failed/cancelled and re-checks at execute time. Completed jobs are never deletable.
- UI tests use the per-test `engine.init_db(tmp)` isolation recipe. Commit after each task/group.
