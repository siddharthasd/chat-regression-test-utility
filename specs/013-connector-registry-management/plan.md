# Implementation Plan: Connector Registry & Management (Module 13)

**Branch**: `013-connector-registry-management` | **Date**: 2026-06-04 | **Spec**: `specs/013-connector-registry-management/spec.md`

**Input**: Feature specification from `specs/013-connector-registry-management/spec.md`

## Summary

`013` is the **tester-facing CRUD UI + service layer** for `ConnectorRegistration` records — the write surface whose read counterpart is `007`'s `ConnectorRegistryReader`. It provides a Flask management surface (list with active/archived/all filter + search, create form, edit form, archive/restore, gated hard-delete) and a non-blocking **Test connection** affordance. The persistence write operations already exist on `009`'s `ConnectorRegistrationRepository` (`create`/`update`/`archive`/`restore`/`hard_delete`, with credential encryption); `013` adds the **business rules** on top — auto-assigned immutable `connectorId` (already in the repo), auth-mode-change credential discard (FR-006), display-name-collision warning, and **hard-delete gating by historical Job references** (FR-019) — plus the Flask blueprint, Jinja templates, and form validation.

It reuses the foundation throughout: `009` repo (writes) + `harness.remote.auth.build_auth_headers` (test-connection auth) + `harness.contract.validate_contract` (test-connection 2xx check, FR-023) + `harness.connector.ConnectorRegistryReader` (the read API, FR-026) + the existing `harness.ui` Flask app factory. **No new runtime dependencies** (Flask + httpx already on `foundation`).

## Technical Context

**Language/Version**: Python 3.11+ (inherited via `foundation`).

**Primary Dependencies** (all already on `foundation`): `flask` (UI + Jinja templates), `httpx` (test-connection POST), plus reused `harness.persistence`, `harness.remote.auth`, `harness.contract`, `harness.connector`. **No new deps** — forms are parsed/validated server-side by hand (no `wtforms`/`flask-wtf`), keeping the dependency surface minimal.

**Storage**: `009`'s `connector_registration` table (no new entity). One new **read query** is needed: count Jobs whose snapshotted `connector_id` matches a registration (for the FR-019 hard-delete gate) — added as `JobRepository.count_by_connector_id` (or an equivalent session query).

**Testing**: `pytest`. Service + form rules unit-tested over `db_session`; test-connection over `httpx.MockTransport`; the Flask routes via Flask's test client (`app.test_client()`), asserting list/filter, create/edit/archive/restore/delete, credential masking, and the hard-delete gate.

**Target Platform**: Local Flask dev server on `127.0.0.1` (single-user, no auth — parent premise). Cross-platform.

**Performance Goals**: List view responsive at 100+ registrations (SC-010); pagination MAY be added later without breaking the filter/search contract.

**Constraints**: Credentials never rendered in plaintext (SC-002, FR-010/011); Test connection never blocks Save and never persists (SC-008, FR-024); `connectorId` immutable (FR-013); hard-delete blocked when historical Jobs reference the registration (FR-019).

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as prior modules).

## Project Structure

### Documentation (this feature)

```text
specs/013-connector-registry-management/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R8)
├── data-model.md        # Phase 1 — form↔descriptor mapping, TestConnectionResult, service ops
├── quickstart.md        # Phase 1 — register/edit/archive/delete + test-connection via the UI
├── contracts/
│   ├── service-api.md             # ConnectorRegistryService surface
│   └── ui-routes.md               # Flask route table + form fields + masking rules
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
src/
└── harness/
    ├── connector_registry/
    │   ├── __init__.py
    │   ├── service.py            # ConnectorRegistryService: CRUD + rules + hard-delete gate (FR-003/006/012/019)
    │   ├── forms.py              # parse + validate form data → auth descriptor; per-mode rules (FR-002/004/005/006)
    │   └── test_connection.py    # run_test_connection(...) -> TestConnectionResult (FR-021–025)
    └── ui/
        ├── __init__.py           # register the connector_registry blueprint in create_app()
        └── connector_registry/
            ├── __init__.py       # Flask Blueprint
            ├── routes.py         # list / new / create / edit / update / archive / restore / delete / test-connection
            └── templates/connector_registry/
                ├── list.html
                ├── form.html
                └── _test_result.html

tests/
├── unit/
│   └── connector_registry/
│       ├── __init__.py
│       ├── test_service.py       # create/update/archive/restore; mode-change discard; hard-delete gate (FR-003/006/019)
│       ├── test_forms.py         # per-mode validation + URL/timeout rules (FR-004/005)
│       └── test_test_connection.py  # categorized outcomes via MockTransport (FR-022/023)
└── integration/
    └── test_connector_registry_ui.py  # Flask test client: routes, masking (SC-002), hard-delete gate (SC-006/007), filter/search (US4)
```

**Structure Decision**: A `connector_registry/` service package (framework-agnostic business logic, fully unit-testable over `db_session`) + a thin Flask blueprint under `ui/connector_registry/` (routes + templates) registered in the existing `create_app()`. This keeps the rules testable without the web layer and mirrors the persistence/UI split used elsewhere.

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001`/`FR-002` (register form fields) | `ui/connector_registry/routes.py` + `templates/form.html` + `forms.py` | `integration/test_connector_registry_ui.py::test_create_form` |
| `FR-003` (save: assign id, encrypt, persist) | `connector_registry/service.py::create` (over `009` repo) | `unit/connector_registry/test_service.py::test_create` |
| `FR-004` (save validation) | `connector_registry/forms.py` | `unit/connector_registry/test_forms.py` |
| `FR-005` (per-mode credential fields) | `connector_registry/forms.py` (form→`{mode,headerName,credential,username,password}`) | `test_forms.py::test_mode_*` |
| `FR-006` (mode-change discards credential) | `connector_registry/service.py::update` | `test_service.py::test_mode_change_discards_credential` |
| `FR-007`–`FR-010` (list/filter/search/columns) | `routes.py` (list) + `templates/list.html` | `test_connector_registry_ui.py::test_list_filter_search` |
| `FR-011`/`FR-012` (edit, masked, preserve ciphertext) | `service.py::update` + `templates/form.html` | `test_service.py::test_update_preserves_ciphertext`; UI masking test |
| `FR-013` (connectorId immutable, read-only) | `service.py` (never writes id) + `form.html` | `test_service.py::test_id_immutable` |
| `FR-014`–`FR-017` (archive/restore; historical unaffected) | `service.py::archive`/`restore` (over `009` repo) | `test_service.py::test_archive_restore`; UI |
| `FR-018`–`FR-020` (hard-delete, gated, id retired) | `service.py::hard_delete` + `JobRepository.count_by_connector_id` | `test_service.py::test_hard_delete_*` (SC-006/007) |
| `FR-021`–`FR-025` (test connection) | `connector_registry/test_connection.py` + route | `unit/connector_registry/test_test_connection.py` |
| `FR-026` (read API for other modules) | **reused from `007`** (`ConnectorRegistryReader`) | covered by `007` |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `test_connector_registry_ui.py::test_registered_connector_listed` (read via `007` reader) |
| `SC-002` | `test_connector_registry_ui.py::test_credential_never_plaintext` (+ `009` at-rest tests) |
| `SC-003` | `test_service.py::test_edit_does_not_change_snapshot` (snapshot immutability is `009`'s) |
| `SC-004` | covered by `007`'s `get_active` (archived excluded) + UI test |
| `SC-005` | `009`/`007` snapshot execution — archived still executable (noted; orchestration in `012`) |
| `SC-006` | `test_service.py::test_hard_delete_blocked_when_referenced` |
| `SC-007` | `test_service.py::test_hard_delete_succeeds_when_unreferenced` |
| `SC-008` | `test_connector_registry_ui.py::test_test_connection_no_side_effects` |
| `SC-009` | `unit/connector_registry/test_test_connection.py::test_categorized_outcomes` |
| `SC-010` | (perf target — pagination deferred; filter/search contract preserved) |

## Foundation Note

`013` is built on **`foundation`** (010+009+006+007+008, 200 tests). It is purely additive: a new `connector_registry/` service package + a Flask blueprint. It reuses 009 (repo writes + encryption), 007 (read facade + the wire-protocol shape for test-connection), 006 (`validate_contract`), and `harness.remote.auth` (test-connection auth header) — no duplication. The only persistence addition is a read-only Job-reference count for the hard-delete gate.

## Complexity Tracking

| Element | Justification |
|---|---|
| Service layer separate from the Flask blueprint | Business rules (mode-change discard, hard-delete gating) must be unit-testable without the web layer; the blueprint stays thin |
| Hand-rolled form validation (no `wtforms`) | One form with conditional per-mode fields; a small validation function avoids a new dependency + CSRF machinery on a single-user localhost tool |
| New `JobRepository.count_by_connector_id` | FR-019 hard-delete gate needs to count historical Jobs referencing the registration; a focused read query, no schema change |
| Test-connection reuses `remote.auth` + `006` + `httpx` | FR-021–023 mirror the connector wire protocol; reusing the shared pieces avoids a parallel HTTP/auth path |
