# Implementation Plan: Evaluator Registry & Management (Module 14)

**Branch**: `014-evaluator-registry-management` | **Date**: 2026-06-04 | **Spec**: `specs/014-evaluator-registry-management/spec.md`

**Input**: Feature specification from `specs/014-evaluator-registry-management/spec.md`

## Summary

`014` is the **evaluator-side twin of `013`**: the CRUD UI + service layer for `EvaluationAgentRegistration`, whose read counterpart is `008`'s `EvaluatorRegistryReader`. It mirrors `013`'s structure (Flask blueprint over `create_app()`, a framework-agnostic service over `009`'s repo, hand-rolled forms, non-blocking Test connection, gated hard-delete) with evaluator-specific differences:
- **Declared scoring dimensions** (an ordered list of strings) replace `013`'s `expectsPerRowPassword` — captured, trimmed, duplicate-warned, and **order-preserved** (drives `004`/`005` column order).
- **`description` is required** (operationally important for evaluators); **default `timeoutSeconds` = 60**.
- **Test connection** POSTs a sample **Standard Evaluation Contract** instance and validates the **response** as an `EvaluationResult` (via `008`'s `validate_evaluation_result`), additionally soft-warning when emitted dimensions diverge from the form's declared list (`008 FR-005a`).

It reuses the foundation (now incl. 013): `009`'s `EvaluationAgentRegistrationRepository` (writes + encryption, already complete), `008`'s `EvaluatorRegistryReader` + `validate_evaluation_result` + `compute_harness_annotations`, `harness.remote.auth` (test-connection auth), `harness.connector.mock.build_contract` (the sample contract body), and the existing Flask app. **No new runtime dependencies.**

## Technical Context

**Language/Version**: Python 3.11+ (inherited via `foundation`).

**Primary Dependencies** (all already on `foundation`): `flask` + `httpx`; reused `harness.persistence`, `harness.evaluator`, `harness.remote.auth`, `harness.connector.mock` (sample contract). **No new deps**; hand-rolled form validation (no `wtforms`/CSRF — single-user localhost, per `013`).

**Storage**: `009`'s `evaluation_agent_registration` table (no new entity). One new read query: `JobRepository.count_by_evaluation_agent_id` for the FR-024 hard-delete gate.

**Testing**: `pytest`. Service + forms over `db_session`; test-connection over `httpx.MockTransport`; Flask routes via `app.test_client()` (with the **per-test `init_db()` isolation fixture** established by `013` — see Foundation Note).

**Target Platform**: Local Flask dev server on `127.0.0.1` (single-user, no auth). Cross-platform.

**Performance Goals**: List responsive at 100+ registrations (SC-013); pagination deferrable.

**Constraints**: Credentials never rendered/persisted in plaintext (SC-002); declared-dimension order preserved exactly (SC-011); Test connection never blocks Save / never persists (SC-009); `evaluationAgentId` immutable (FR-018); hard-delete gated by Job references (FR-024).

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as prior modules).

## Project Structure

### Documentation (this feature)

```text
specs/014-evaluator-registry-management/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R8)
├── data-model.md        # Phase 1 — form↔descriptor, dimensions, TestConnectionResult, service ops
├── quickstart.md        # Phase 1 — register/edit/dimensions/archive/delete + test-connection
├── contracts/
│   ├── service-api.md             # EvaluatorRegistryService surface
│   └── ui-routes.md               # Flask route table + form fields (incl. dimensions) + masking
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
src/
└── harness/
    ├── evaluator_registry/
    │   ├── __init__.py
    │   ├── service.py            # EvaluatorRegistryService: CRUD + rules + hard-delete gate (FR-003/006/019/024)
    │   ├── forms.py              # parse + validate (incl. ordered dimensions: trim, empty-reject, dup-warn) (FR-002/004/005/007-011)
    │   └── test_connection.py    # run_test_connection(...) -> TestConnectionResult (FR-026-030)
    └── ui/
        ├── __init__.py           # register the evaluator_registry blueprint in create_app()
        └── evaluator_registry/
            ├── __init__.py       # Flask Blueprint
            ├── routes.py         # list / new / create / edit / update / archive / restore / delete / test-connection
            └── templates/evaluator_registry/
                ├── list.html
                ├── form.html
                └── _test_result.html

tests/
├── unit/
│   └── evaluator_registry/
│       ├── __init__.py
│       ├── test_service.py       # create/update/archive/restore; mode-change discard; dimensions; hard-delete gate
│       ├── test_forms.py         # per-mode + URL/timeout + dimension trim/empty/dup rules
│       └── test_test_connection.py  # EvaluationResult-validated outcomes + unexpected-dim soft-warning via MockTransport
└── integration/
    └── test_evaluator_registry_ui.py  # Flask test client: routes, masking, dimension preview, hard-delete gate
```

**Structure Decision**: Mirror `013` exactly — `evaluator_registry/` service package + thin `ui/evaluator_registry/` blueprint registered in `create_app()`. The only structural novelty vs `013` is the dimension-list handling in `forms.py` and the list view's dimension preview.

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001`/`FR-002` (register form) | `ui/evaluator_registry/routes.py` + `templates/form.html` + `forms.py` | `integration/test_evaluator_registry_ui.py::test_create_form` |
| `FR-003` (save: id, encrypt, persist) | `evaluator_registry/service.py::create` (over `009`) | `unit/evaluator_registry/test_service.py::test_create` |
| `FR-004` (save validation, incl. empty dimension) | `evaluator_registry/forms.py` | `unit/evaluator_registry/test_forms.py` |
| `FR-005`/`FR-006` (auth modes + mode-change discard) | `forms.py` + `service.py::update` | `test_forms.py::test_mode_*`; `test_service.py::test_mode_change` |
| `FR-007`–`FR-011` (declared dimensions: add/remove/reorder, trim, empty-reject, dup-warn, order-preserve) | `forms.py::parse_dimensions` + `form.html` | `test_forms.py::test_dimensions_*` (SC-011) |
| `FR-012`–`FR-015` (list/filter/search/columns + dim preview) | `routes.py` (list) + `templates/list.html` | `test_evaluator_registry_ui.py::test_list_filter_search` |
| `FR-016`/`FR-017` (edit, masked, preserve ciphertext) | `service.py::update` + `form.html` | `test_service.py::test_update_preserves`; UI masking |
| `FR-018` (id immutable) | `service.py` (never writes id) | `test_service.py::test_id_immutable` |
| `FR-019`–`FR-022` (archive/restore) | `service.py::archive`/`restore` | `test_service.py::test_archive_restore` |
| `FR-023`–`FR-025` (hard-delete gated, id retired) | `service.py::hard_delete` + `JobRepository.count_by_evaluation_agent_id` | `test_service.py::test_hard_delete_*` (SC-007/008) |
| `FR-026`–`FR-030` (test connection → EvaluationResult validation + dim soft-warning) | `evaluator_registry/test_connection.py` | `unit/evaluator_registry/test_test_connection.py` |
| `FR-031` (read API) | **reused from `008`** (`EvaluatorRegistryReader`) | covered by `008` |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `test_evaluator_registry_ui.py::test_registered_listed` (via `008` reader) |
| `SC-002` | `test_evaluator_registry_ui.py::test_credential_never_plaintext` (+ `009` at-rest tests) |
| `SC-003`/`SC-004` | snapshot immutability is `009`'s; `test_service.py` (edit doesn't mutate snapshots) |
| `SC-005`/`SC-006` | `008`'s `get_active` (archived excluded) + snapshot execution (noted; `012`) |
| `SC-007` | `test_service.py::test_hard_delete_blocked_when_referenced` |
| `SC-008` | `test_service.py::test_hard_delete_succeeds_when_unreferenced` |
| `SC-009` | `test_evaluator_registry_ui.py::test_test_connection_no_side_effects` |
| `SC-010` | `unit/evaluator_registry/test_test_connection.py::test_categorized_outcomes` |
| `SC-011` | `test_forms.py::test_dimensions_order_preserved` + `test_service.py` round-trip |
| `SC-012` | `test_service.py::test_empty_dimensions_ok` |
| `SC-013` | (perf target — pagination deferred) |

## Foundation Note

`014` is built on **`foundation`** (now 010+009+006+007+008+013, 231 tests). It is purely additive and **mirrors `013`**. Reuses: `009` repo (writes/encryption), `008` `EvaluatorRegistryReader` + `validate_evaluation_result` + `compute_harness_annotations`, `harness.remote.auth` (auth header), `harness.connector.mock.build_contract` (sample contract for test-connection). The only persistence addition is `JobRepository.count_by_evaluation_agent_id` (sibling of `013`'s `count_by_connector_id`).

**Inherit `013`'s UI test-isolation fixture**: `create_app()`'s `initialize_harness()` early-returns once the identity singleton is set, so the UI test fixture must call `engine.init_db(tmp_path/...)` explicitly per test (+ reset the encryption key cache) to get an isolated DB. (Documented from `013`'s implementation.)

## Complexity Tracking

| Element | Justification |
|---|---|
| Service layer separate from blueprint | Rules (dimension parsing, mode-change discard, hard-delete gate) unit-testable without the web layer |
| Ordered-dimension input | FR-007/011 require add/remove/reorder with preserved order; a newline-per-dimension textarea preserves order server-rendered without JS (drag-drop is a deferred nicety) |
| New `JobRepository.count_by_evaluation_agent_id` | FR-024 gate; focused read query, sibling of `013`'s connector count |
| Test-connection validates the *response* as EvaluationResult | FR-029 — reuses `008`'s `validate_evaluation_result` + `compute_harness_annotations`; the sample request body reuses `harness.connector.mock.build_contract` |
