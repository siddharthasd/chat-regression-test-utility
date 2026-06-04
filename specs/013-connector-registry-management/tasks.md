---
description: "Task list for Connector Registry & Management (Module 13)"
---

# Tasks: Connector Registry & Management (Module 13)

**Input**: Design documents from `specs/013-connector-registry-management/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R8) ✅, data-model.md ✅, contracts/ (service-api.md, ui-routes.md) ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `013-connector-registry-management` on `foundation` (010+009+006+007+008). Reuses 009 repo (writes/encryption), 007 `ConnectorRegistryReader` (read API), `harness.remote.auth` + 006 `validate_contract` + `httpx` (test-connection), and the existing `harness.ui.create_app()`. **No new deps.** Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US5 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [X] T001 Create scaffold: `src/harness/connector_registry/__init__.py`, `src/harness/ui/connector_registry/__init__.py`, `src/harness/ui/connector_registry/templates/connector_registry/` (dir), `tests/unit/connector_registry/__init__.py`
- [X] T002 Add a `[tool.setuptools.package-data]` entry for the blueprint templates (`"harness.ui.connector_registry" = ["templates/connector_registry/*.html"]`) in `pyproject.toml`; `python -m pip install -e ".[dev]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the service layer, form validation, test-connection, the hard-delete count query, and the blueprint wiring that every story builds on.

- [X] T003 [P] Add `count_by_connector_id(connector_id: str) -> int` to `src/harness/persistence/repositories/job.py` (`SELECT count FROM job WHERE connector_id = ?`) for the FR-019 gate
- [X] T004 [P] Implement `src/harness/connector_registry/forms.py::parse_connector_form(form) -> tuple[dict | None, dict[str,str]]`: required fields, URL syntax, timeout range 1–300, per-mode credential rules → canonical descriptor (`credential`/`password` keys) (FR-002/004/005)
- [X] T005 [P] Implement `src/harness/connector_registry/test_connection.py`: `TestConnectionResult` dataclass + `run_test_connection(endpoint_url, decrypted_descriptor, timeout_seconds, expects_per_row_password, *, client=None)` — sample body, `harness.remote.auth.build_auth_headers`, `httpx` POST, categorize, 2xx → `harness.contract.validate_contract` (FR-021–025); never persists
- [X] T006 Implement `src/harness/connector_registry/service.py`: `RegistrationInUseError` + `ConnectorRegistryService` (`create`/`update`[replace + mode-change discard]/`archive`/`restore`/`hard_delete`[gated via T003]/`count_referencing_jobs`) over `009`'s `ConnectorRegistrationRepository` (FR-003/006/014/016/019). Depends on T003, T004.
- [X] T007 Re-export `ConnectorRegistryService`, `RegistrationInUseError`, `parse_connector_form`, `run_test_connection`, `TestConnectionResult` from `src/harness/connector_registry/__init__.py`
- [X] T008 Create the Flask blueprint `src/harness/ui/connector_registry/__init__.py` (with `template_folder`) + empty `routes.py`, and register it in `src/harness/ui/__init__.py::create_app()`

**Checkpoint**: service + forms + test-connection unit-testable; blueprint mounts.

---

## Phase 3: User Story 1 — Register a new connector (Priority: P1) 🎯 MVP

**Goal**: A tester registers a connector via a form; it persists (encrypted) and becomes selectable.

**Independent Test**: POST a valid create form → a `ConnectorRegistration` persists with `archived=false`; it shows in the list and via `007`'s `get_active`.

### Implementation for User Story 1

- [X] T009 [US1] `routes.py`: `GET /connectors/new` (render create form), `POST /connectors` (validate via `forms`, `service.create`, redirect to list / re-render with errors), `POST /connectors/test-connection` (assemble descriptor, `run_test_connection`, return `_test_result.html`); templates `form.html` + `_test_result.html`

### Tests for User Story 1

- [X] T010 [P] [US1] `tests/unit/connector_registry/test_forms.py`: per-mode credential rules, URL syntax, timeout range, empty-required (FR-004/005)
- [X] T011 [US1] `tests/unit/connector_registry/test_service.py`: `create` assigns id + encrypts + persists (FR-003); `tests/integration/test_connector_registry_ui.py`: create route persists + appears via reader (SC-001)

**Checkpoint**: MVP — a connector can be registered through the UI.

---

## Phase 4: User Story 2 — Edit a registration (Priority: P1)

**Goal**: Edit fields; rotate credentials; mode change discards old credential; historical snapshots unaffected.

### Implementation for User Story 2

- [X] T012 [US2] `routes.py` (same file): `GET /connectors/<id>/edit` (pre-populated, secrets masked, read-only `connectorId`, "Replace credential" toggle), `POST /connectors/<id>` (`service.update`); extend `form.html` for edit mode

### Tests for User Story 2

- [X] T013 [US2] `test_service.py`: `update` preserves ciphertext unless replaced; mode change requires + discards (FR-006/011/012); integration: edit form masks secrets

**Checkpoint**: Edit + credential rotation work; snapshot isolation (009) intact.

---

## Phase 5: User Story 3 — Archive / Restore (Priority: P1)

**Goal**: Soft-delete hides from wizard + default list but keeps history; restore re-enables.

### Implementation for User Story 3

- [X] T014 [US3] `routes.py` (same file): `POST /connectors/<id>/archive`, `POST /connectors/<id>/restore` (+ bulk ids); list-row action buttons + "Archived" badge in `list.html`

### Tests for User Story 3

- [X] T015 [US3] `test_service.py`: `archive`/`restore` set flags/timestamps (FR-014/016); integration: archived absent from default list, present under Archived filter; restore round-trip

**Checkpoint**: Archival lifecycle works; archived excluded from `007`'s `get_active`.

---

## Phase 6: User Story 4 — List, filter, inspect (Priority: P2)

**Goal**: List with active/archived/all filter + display-name search; columns mask credentials; empty state.

### Implementation for User Story 4

- [X] T016 [US4] `routes.py` (same file): `GET /connectors` with `filter`/`q` params (default active, alphabetical); `list.html` (columns per FR-010, masked creds, badges, empty-state CTA)

### Tests for User Story 4

- [X] T017 [P] [US4] `tests/integration/test_connector_registry_ui.py`: filter Active/Archived/All + substring search (FR-007-009); credentials never rendered in plaintext (SC-002)

**Checkpoint**: Registry browsable/searchable at scale.

---

## Phase 7: User Story 5 — Hard-delete (gated) (Priority: P3)

**Goal**: Permanent delete only when no historical Job references the registration.

### Implementation for User Story 5

- [X] T018 [US5] `routes.py` (same file): `POST /connectors/<id>/delete` — confirm dialog; on `RegistrationInUseError` re-render with the referencing-job count message; else delete + redirect (FR-018/019)

### Tests for User Story 5

- [X] T019 [US5] `test_service.py`: `hard_delete` blocked when referenced (SC-006) and succeeds when unreferenced (SC-007); integration: delete route gating message

**Checkpoint**: Gated hard-delete complete.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T020 [P] `tests/unit/connector_registry/test_test_connection.py`: categorized outcomes (valid/invalid_contract/http_error/unreachable/timeout) via `httpx.MockTransport`; no side effects (FR-022/023, SC-008/009)
- [X] T021 [P] `python -m ruff check src tests --fix`; resolve findings
- [X] T022 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 200 tests still pass + adequate `connector_registry/` coverage
- [X] T023 [P] Execute `specs/013-connector-registry-management/quickstart.md`; file discrepancies
- [X] T024 [P] Verify FR→File and SC matrices; confirm `CLAUDE.md` marker → `013` plan

---

## Dependencies & Execution Order

- **Setup** → no deps. **Foundational** → blocks all stories (service/forms/test-connection/count/blueprint).
- **US1 (P3)** → create routes + form (also adds the test-connection route used by edit later). MVP.
- **US2 (P4)** → edit routes; extends `form.html` + `routes.py`.
- **US3 (P5)** → archive/restore routes + list actions.
- **US4 (P6)** → list/filter/search route + `list.html`.
- **US5 (P7)** → delete route (uses the foundational gate).
- **Polish** → after targeted stories.

### Critical path
Setup → Foundational → US1 → US2 → US3 → US4 → US5 → Polish. `routes.py` is one file grown across US1–US5 → those tasks are **sequential**; `service.py` is built once (T006) and only *tested* per story.

### Parallel opportunities
- Foundational: T003 ‖ T004 ‖ T005 (distinct files); T006 depends on T003/T004; T007/T008 after.
- Distinct test files are [P]: `test_forms.py`, `test_test_connection.py`, and the US4 integration test. `test_service.py` and `test_connector_registry_ui.py` are shared across stories → sequential within.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 → **STOP & VALIDATE**: register a connector through the UI (create route persists; appears via `007`'s reader).

### Incremental delivery
US1 (register) → US2 (edit) → US3 (archive/restore) → US4 (list/filter) → US5 (hard-delete) → Polish.

---

## Notes

- `013` is a service + Flask UI over existing persistence — **no new persisted entity** and **no new deps**. The only persistence addition is the read-only `count_by_connector_id`.
- Reuse, don't duplicate: read API = `007`'s `ConnectorRegistryReader`; test-connection auth = `harness.remote.auth`; 2xx validation = `006`'s `validate_contract`; credential encryption = `009`'s repo.
- Credentials are never rendered or persisted in plaintext (SC-002); test-connection never blocks Save and never persists (SC-008). Commit after each task/group.
