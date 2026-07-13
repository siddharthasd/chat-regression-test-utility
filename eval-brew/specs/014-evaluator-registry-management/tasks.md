---
description: "Task list for Evaluator Registry & Management (Module 14)"
---

# Tasks: Evaluator Registry & Management (Module 14)

**Input**: Design documents from `specs/014-evaluator-registry-management/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R8) ✅, data-model.md ✅, contracts/ (service-api.md, ui-routes.md) ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `014-evaluator-registry-management` on `foundation` (010+009+006+007+008+013). **Mirrors 013.** Reuses 009 repo (writes/encryption), 008 `EvaluatorRegistryReader` + `validate_evaluation_result` + `compute_harness_annotations`, `harness.remote.auth`, `harness.connector.mock.build_contract` (test-connection sample), and `create_app()`. **No new deps.** Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US6 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [X] T001 Create scaffold: `src/harness/evaluator_registry/__init__.py`, `src/harness/ui/evaluator_registry/__init__.py`, `src/harness/ui/evaluator_registry/templates/evaluator_registry/` (dir), `tests/unit/evaluator_registry/__init__.py`
- [X] T002 Add `[tool.setuptools.package-data]` entry `"harness.ui.evaluator_registry" = ["templates/evaluator_registry/*.html"]` in `pyproject.toml`; `python -m pip install -e ".[dev]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T003 [P] Add `count_by_evaluation_agent_id(evaluation_agent_id: str) -> int` to `src/harness/persistence/repositories/job.py` (FR-024 gate)
- [X] T004 [P] Implement `src/harness/evaluator_registry/forms.py::parse_evaluator_form(form, *, require_credential=True)`: required fields incl. **description**, URL syntax, timeout range 1–600, per-mode creds → canonical descriptor, and `parse_dimensions` (newline textarea → trimmed ordered list, drop blanks, duplicate → non-blocking warning, empty OK) (FR-002/004/005/007-011)
- [X] T005 [P] Implement `src/harness/evaluator_registry/test_connection.py`: `TestConnectionResult` + `run_test_connection(endpoint_url, decrypted_descriptor, timeout_seconds, declared_dimensions, *, client=None)` — sample contract (`harness.connector.mock.build_contract`, `utteranceId="test-utt"`), `harness.remote.auth.build_auth_headers`, `httpx` POST, categorize, 2xx → `harness.evaluator.validate_evaluation_result` + dimension-divergence `warning` via `compute_harness_annotations` (FR-026–030); never persists
- [X] T006 Implement `src/harness/evaluator_registry/service.py`: `RegistrationInUseError` + `EvaluatorRegistryService` (`create`/`update`[replace + mode-change]/`archive`/`restore`/`list_registrations`/`hard_delete`[gated via T003]/`count_referencing_jobs`) over `009`'s `EvaluationAgentRegistrationRepository` (FR-003/006/019/024). Depends on T003, T004.
- [X] T007 Re-export `EvaluatorRegistryService`, `RegistrationInUseError`, `parse_evaluator_form`, `run_test_connection`, `TestConnectionResult` from `src/harness/evaluator_registry/__init__.py`
- [X] T008 Create the Flask blueprint `src/harness/ui/evaluator_registry/__init__.py` (`template_folder`) + empty `routes.py`, and register it in `src/harness/ui/__init__.py::create_app()`

**Checkpoint**: service + forms + test-connection unit-testable; blueprint mounts.

---

## Phase 3: User Story 1 — Register a new evaluator (Priority: P1) 🎯 MVP

- [X] T009 [US1] `routes.py`: `GET /evaluators/new`, `POST /evaluators` (validate via `forms`, `service.create`, redirect / re-render errors), `POST /evaluators/test-connection` (assemble descriptor + declared dims, `run_test_connection`, return `_test_result.html`); templates `form.html` (with dimensions textarea) + `_test_result.html`
- [X] T010 [P] [US1] `tests/unit/evaluator_registry/test_forms.py`: per-mode rules, URL, timeout, required description, empty-required (FR-002/004/005)
- [X] T011 [US1] `tests/unit/evaluator_registry/test_service.py`: `create` assigns id + encrypts + persists (FR-003); `tests/integration/test_evaluator_registry_ui.py`: create route persists + lists (SC-001)

**Checkpoint**: MVP — an evaluator can be registered through the UI.

---

## Phase 4: User Story 2 — Edit a registration (Priority: P1)

- [X] T012 [US2] `routes.py` (same file): `GET /evaluators/<id>/edit` (masked secrets, read-only id, dimensions prefilled), `POST /evaluators/<id>` (`service.update`); extend `form.html` for edit mode
- [X] T013 [US2] `test_service.py`: `update` preserves ciphertext unless replaced; mode change discards (FR-006/016/017); integration: edit masks secrets

**Checkpoint**: Edit + credential rotation work; snapshot isolation (009) intact.

---

## Phase 5: User Story 3 — Declare & refine scoring dimensions (Priority: P1)

- [X] T014 [P] [US3] `tests/unit/evaluator_registry/test_forms.py` (same file): `parse_dimensions` trims, drops blanks, preserves order (SC-011), warns on duplicates (FR-009), allows empty list (FR-010); rejects whitespace-only entries (FR-008)
- [X] T015 [US3] `test_service.py`: dimensions persist + read back in exact order via `008` reader (SC-011); empty list accepted (SC-012)

**Checkpoint**: Dimension capture is order-faithful and validated.

---

## Phase 6: User Story 4 — Archive / Restore (Priority: P1)

- [X] T016 [US4] `routes.py` (same file): `POST /evaluators/<id>/archive`, `POST /evaluators/<id>/restore` (+ bulk); list-row buttons + "Archived" badge in `list.html`
- [X] T017 [US4] `test_service.py`: `archive`/`restore` (FR-019/021); integration: archived absent from active list, present under Archived filter

**Checkpoint**: Archival lifecycle works; archived excluded from `008`'s `get_active`.

---

## Phase 7: User Story 5 — List, filter, inspect (Priority: P2)

- [X] T018 [US5] `routes.py` (same file): `GET /evaluators` with `filter`/`q`; `list.html` (columns per FR-015, masked creds, **dimension preview** first 3 + `+ N more`, badges, empty-state CTA)
- [X] T019 [P] [US5] `tests/integration/test_evaluator_registry_ui.py`: filter Active/Archived/All + search (FR-012-014); credentials never plaintext (SC-002); dimension preview present

**Checkpoint**: Registry browsable/searchable; dimensions previewed.

---

## Phase 8: User Story 6 — Hard-delete (gated) (Priority: P3)

- [X] T020 [US6] `routes.py` (same file): `POST /evaluators/<id>/delete` — confirm; on `RegistrationInUseError` re-render with referencing-job count; else delete + redirect (FR-023/024)
- [X] T021 [US6] `test_service.py`: `hard_delete` blocked when referenced (SC-007), succeeds when unreferenced (SC-008); integration: delete route gating

**Checkpoint**: Gated hard-delete complete.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T022 [P] `tests/unit/evaluator_registry/test_test_connection.py`: categorized outcomes (valid/invalid_result/http_error/unreachable/timeout) + dimension-divergence soft warning, via `httpx.MockTransport`; no side effects (FR-028/029, SC-009/010)
- [X] T023 [P] `python -m ruff check src tests --fix`; resolve findings
- [X] T024 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 231 tests still pass + adequate `evaluator_registry/` coverage
- [X] T025 [P] Execute `specs/014-evaluator-registry-management/quickstart.md`; file discrepancies
- [X] T026 [P] Verify FR→File and SC matrices; confirm `CLAUDE.md` marker → `014` plan

---

## Dependencies & Execution Order

- **Setup** → no deps. **Foundational** → blocks all stories (service/forms/test-connection/count/blueprint).
- **US1 (P3)** → create routes + form (+ test-connection route). MVP.
- **US2 (P4)** → edit routes; extends `routes.py` + `form.html`.
- **US3 (P5)** → test-only over the foundational dimension parsing (`forms`/`service`).
- **US4 (P6)** → archive/restore routes + list actions.
- **US5 (P7)** → list/filter/search route + `list.html` (dimension preview).
- **US6 (P8)** → delete route (uses the foundational gate).
- **Polish** → after targeted stories.

### Critical path
Setup → Foundational → US1 → US2 → US3 → US4 → US5 → US6 → Polish. `routes.py` is one file grown across US1/US2/US4/US5/US6 → those tasks are **sequential**; `service.py`/`forms.py` built once (T004/T006) and only *tested* per story.

### Parallel opportunities
- Foundational: T003 ‖ T004 ‖ T005; T006 depends on T003/T004; T007/T008 after.
- Distinct test files are [P]: `test_forms.py`, `test_test_connection.py`, and the US5 integration test. `test_service.py` + `test_evaluator_registry_ui.py` are shared across stories → sequential within.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: register an evaluator through the UI (persists; lists via `008`'s reader).

### Incremental delivery
US1 → US2 → US3 → US4 → US5 → US6 → Polish.

---

## Notes

- Mirror 013's `connector_registry` implementation; the only novelties are dimension handling and the EvaluationResult-aware test-connection.
- Reuse, don't duplicate: read API = `008`'s `EvaluatorRegistryReader`; test-connection validation = `008`'s `validate_evaluation_result`; sample contract = `007`'s `mock.build_contract`; auth = `harness.remote.auth`; encryption = `009`'s repo.
- UI tests must use the per-test `engine.init_db(tmp)` isolation fixture (from 013) — `create_app()` won't re-run `init_db` once identity is set. Commit after each task/group.
