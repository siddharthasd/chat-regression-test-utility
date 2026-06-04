---
description: "Task list for Job Creation & Configuration Wizard (Module 9)"
---

# Tasks: Job Creation & Configuration Wizard (Module 9)

**Input**: Design documents from `specs/003-job-creation-wizard/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R8) ✅, data-model.md ✅, contracts/ui-routes.md ✅, quickstart.md ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `003-job-creation-wizard` on `foundation` (006/007/008/009/010/011/012/013/014). **Server-rendered Flask, the surface that ties the backend together.** Reuses 009 `JobRepository` (`create_draft`/`set_connector_snapshot`/`set_evaluator_snapshot`/`transition_to_queued`), 007/008 readers (`list_active`/`get`), 011 `csv_upload.process_upload`, 012 `orchestrator.enqueue_job`, 010 `IdentityContext`/`password_store`, and the existing standalone-HTML template style + per-test `engine.init_db(tmp)` isolation. **No new deps.** Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US5 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [ ] T001 Create scaffold: `src/harness/ui/wizard/__init__.py` (exports `bp`), `src/harness/ui/wizard/routes.py` (empty `bp = Blueprint("wizard", __name__, template_folder="templates")`), `src/harness/ui/wizard/steps.py` (empty), `src/harness/ui/wizard/templates/wizard/` (dir).
- [ ] T002 Register the wizard blueprint in `src/harness/ui/__init__.py::create_app()`; add `"harness.ui.wizard" = ["templates/wizard/*.html"]` to `[tool.setuptools.package-data]` in `pyproject.toml`; `python -m pip install -e ".[dev]"`.

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T003 Implement `src/harness/ui/wizard/steps.py`: step-completion predicates over a Job + the two readers (S1 name, S2 `total_utterance_count`, S3 connector snapshot + active, S4 evaluator snapshot + active), `lowest_incomplete_step(job, conn_reader, eval_reader) -> int`, `password_coordination_ok(job) -> bool` (true unless `expects_per_row_password` and store empty), and a `review_view(job)` masked projection for Step 5 (auth-mode label only, never credentials). (FR-014/015/017, data-model.md §2/§3/§4)

**Checkpoint**: pure predicate/projection layer unit-usable; blueprint mounts (empty).

---

## Phase 3: User Story 1 — Create a job end-to-end (Priority: P1) 🎯 MVP

- [ ] T004 [US1] `routes.py`: `GET /jobs/new` + `POST /jobs` (name required → `create_draft(name, desc, IdentityContext.current().value)`, redirect step2; empty name → 400 re-render) + `GET /jobs/<id>` resume (redirect to `lowest_incomplete_step`) + `GET/POST /jobs/<id>/step1` (edit name/desc); templates `step1.html`. (FR-001/002/003/004/017)
- [ ] T005 [US1] `routes.py` (same file): `GET/POST /jobs/<id>/step2` — multipart `csv_file` → `tempfile` → `process_upload(job_id, tmp, filename=secure_filename(...))` → `os.unlink` in `finally`; success shows summary (utterance + distinct-testId count) + redirect step3, failure re-renders per-row `errors` (400); `step2.html`. (FR-005/006)
- [ ] T006 [US1] `routes.py` (same file): `GET/POST /jobs/<id>/step3` — dropdown from `ConnectorRegistryReader.list_active()`, `set_connector_snapshot` on Next, then password coordination (if `expects_per_row_password` and `not password_store.job_has_entries` → redirect step2 with message, else step3→step4); `step3.html`. (FR-007/009)
- [ ] T007 [US1] `routes.py` (same file): `GET/POST /jobs/<id>/step4` — dropdown from `EvaluatorRegistryReader.list_active()` (description + dimensions shown), `set_evaluator_snapshot` on Next → step5; `step4.html`. (FR-010/012)
- [ ] T008 [US1] `routes.py` (same file): `GET /jobs/<id>/step5` (masked `review_view`, `start_ready` flag) + `POST /jobs/<id>/start` (`transition_to_queued` in `get_session`; on 009 guard raise → 409 re-render Step 5; success → `enqueue_job(job_id)` [module global, patchable] → redirect) + `GET /jobs/<id>/started`; templates `step5.html`, `started.html`. (FR-014/015/016)
- [ ] T009 [US1] `tests/integration/test_wizard_ui.py`: full create→start happy path with seeded active connector+evaluator registrations + a valid CSV → Job ends `queued`, `started_at` set, snapshots byte-equal to the registrations (SC-011), `enqueue_job` spy called for the job id (SC-001/008). Uses per-test `engine.init_db(tmp)` + `password_store._reset_for_tests()` + `monkeypatch` of `wizard.routes.enqueue_job`.

**Checkpoint**: MVP — a tester can create + start a job through all five steps.

---

## Phase 4: User Story 2 — Resume a Draft exactly where left (Priority: P2)

- [ ] T010 [US2] `tests/integration/test_wizard_ui.py` (same file): complete Steps 1–2, then `GET /jobs/<id>` → 302 to step3 with Steps 1–2 pre-filled (SC-003); a Draft whose snapshotted connector was archived after selection → reaching step3 surfaces the unavailable message + requires re-select, Draft not deleted (US2 sc3, SC-010).

**Checkpoint**: Resume opens at the lowest-incomplete step; archived selections handled.

---

## Phase 5: User Story 3 — Free Back/Next without data loss (Priority: P2)

- [ ] T011 [US3] `tests/integration/test_wizard_ui.py` (same file): complete Steps 1–4, Back to step3, change the connector → snapshot replaced, evaluator selection preserved; change name on step1 → later steps intact (SC-002, FR-018).

**Checkpoint**: Navigation preserves data; re-selection replaces the right snapshot only.

---

## Phase 6: User Story 4 — CSV validation gate at Step 2 (Priority: P2)

- [ ] T012 [US4] `tests/integration/test_wizard_ui.py` (same file): malformed CSV at step2 → per-row errors rendered, Next not offered (no redirect to step3), `total_utterance_count` unset; clean CSV → summary with counts + advances (SC-004, FR-005/006).

**Checkpoint**: Step 2 is an honest validation gate backed by 011.

---

## Phase 7: User Story 5 — Empty-registry affordance (Priority: P2)

- [ ] T013 [US5] `tests/integration/test_wizard_ui.py` (same file): with zero active connector registrations, step3 hides the dropdown + shows a link to `connector_registry.new_connector`, Next disabled; same for step4 → `evaluator_registry` (SC-007, FR-008/011). Draft preserved across the round-trip.

**Checkpoint**: Fresh-install path is navigable.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T014 [P] `tests/integration/test_wizard_ui.py` (same file): no-secret-rendered — a connector with a distinctive bearer token never appears in the Step 5 HTML (only the auth-mode label) (FR-020); password-coordination — selecting an `expects_per_row_password` connector after a password-less CSV bounces to step2 with a message and disables Start.
- [ ] T015 [P] `python -m ruff check src tests --fix`; resolve findings (line-length 100).
- [ ] T016 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 313 tests still pass + adequate `ui/wizard/` coverage.
- [ ] T017 [P] Execute `specs/003-job-creation-wizard/quickstart.md`; verify FR→File + SC matrices; confirm `CLAUDE.md` marker → `003` plan.

---

## Dependencies & Execution Order

- **Setup** (T001–T002) → no deps. **Foundational** (T003) → predicates/projection block the stories.
- **US1 (P3)** → routes + templates for all five steps + start (the MVP). `routes.py` is one file grown across T004–T008 → **sequential**.
- **US2/US3/US4/US5 (P4–P7)** → tests over behavior already built in US1 (resume resolver, snapshot replace, validation gate, empty-state) — the `test_wizard_ui.py` file is extended per story → sequential within.
- **Polish** → after the stories.

### Critical path
Setup → Foundational → US1 (T004→T005→T006→T007→T008→T009) → US2 → US3 → US4 → US5 → Polish.

### Parallel opportunities
- T015/T017 are [P] (lint, docs) once tests pass. The route tasks and the single integration test file are sequential.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: create a job through all five steps and Start it (job `queued`, enqueue signalled, snapshots byte-equal — SC-001/008/011).

### Incremental delivery
US1 → US2 → US3 → US4 → US5 → Polish.

---

## Notes

- The Draft Job IS the wizard state; the current step is derived (lowest-incomplete), never stored — resume is just "compute cursor + redirect" (FR-017).
- 011 doesn't retain the CSV, so the connector password requirement is coordinated by re-upload, not silent re-validation (plan §per-row-password coordination).
- The wizard never re-encrypts: snapshots copy the registration's ciphertext verbatim via 009's setters (FR-009/012). Step 5 renders only auth-mode labels — no credential bytes (FR-020).
- Start reuses 009's `transition_to_queued` as the FR-015/016 gate (validates presence + active registrations; rollback on failure). `enqueue_job` is a patchable module global for deterministic SC-008 tests.
- UI tests use the per-test `engine.init_db(tmp)` isolation recipe (from 013/014) + `password_store._reset_for_tests()`. Commit after each task/group.
