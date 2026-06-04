---
description: "Task list for Connector Framework (Module 4)"
---

# Tasks: Connector Framework (Module 4)

**Input**: Design documents from `specs/007-connector-framework/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R9) ✅, data-model.md ✅, contracts/ (wire-protocol.md, client-api.md) ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix in plan.md).

**Branch base**: `007-connector-framework` is already on the `foundation` tree (010+009+006 present) — **no graft needed**. 007 reuses `009` (registry repo + encryption) and `006` (`validate_contract`). Paths are relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US4 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [ ] T001 Add `httpx>=0.27` to `[project].dependencies` in `pyproject.toml` (research R9)
- [ ] T002 Create package scaffold: `src/harness/connector/__init__.py` and `tests/unit/connector/__init__.py`
- [ ] T003 Reinstall and confirm `import httpx` resolves: `python -m pip install -e ".[dev]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The dispatch input/output types, auth-header builder, and the full per-row HTTP client every story builds on.

**⚠️ CRITICAL**: No user-story phase begins until this is complete.

- [ ] T004 [P] Implement `src/harness/connector/result.py`: frozen dataclasses `ConnectorSnapshot`, `UtteranceRow`, `ConnectorResult` (per contracts/client-api.md, data-model.md)
- [ ] T005 [P] Implement `src/harness/connector/auth.py`: `build_auth_headers(descriptor)` for `none`/`bearer`/`api-key-header`/`basic` (unknown → `ValueError`), and `_decrypt_descriptor(descriptor)` reusing `harness.persistence.encryption.decrypt_credential` on the `credential`/`password` subfields (FR-007a-d/FR-008; R4/R5)
- [ ] T006 Implement `src/harness/connector/client.py::dispatch_utterance(snapshot, row, *, client=None)`: decrypt descriptor (→ `connector_auth` on `HarnessKeyMismatchError`, no request sent), build body `{testId, utteranceText, password?}` (password iff `expects_per_row_password`, FR-002/017), add auth header, `httpx` POST with `timeout=timeout_seconds` (no retry), map failures to `connector_transport`/`connector_response`/`connector_normalization`, validate 2xx JSON via `harness.contract.validate_contract` → `ConnectorResult` (FR-001..006; R3/R7/R8). Depends on T004, T005.
- [ ] T007 Re-export `dispatch_utterance`, `ConnectorResult`, `ConnectorSnapshot`, `UtteranceRow`, `build_auth_headers` from `src/harness/connector/__init__.py`

**Checkpoint**: A row can be dispatched (via an injected `httpx.MockTransport` client) and outcomes categorized.

---

## Phase 3: User Story 1 — Run a row through a registered connector (Priority: P1) 🎯 MVP

**Goal**: A dispatched row issues exactly one POST and yields a validated contract (or a categorized failure).

**Independent Test**: With an `httpx.MockTransport` returning a conformant contract, `dispatch_utterance` returns `ok=True` with the contract; one request issued; body shape correct. (The real-server end-to-end lands in US4 once the mock exists.)

### Tests for User Story 1

- [ ] T008 [P] [US1] `tests/unit/connector/test_client.py`: success → `ok=True` + contract (FR-003); body has/omits `password` per `expects_per_row_password` (FR-002); exactly one request issued (SC-006) — via `httpx.MockTransport`
- [ ] T009 [US1] `tests/unit/connector/test_client.py` (same file): errorStage mapping — non-2xx → `connector_response` (SC-008), invalid/non-conformant 2xx body → `connector_normalization` (SC-009), timeout → `connector_transport` (SC-010), no retry (FR-006)

**Checkpoint**: MVP dispatch logic proven at the unit level.

---

## Phase 4: User Story 2 — Add a connector with zero core changes (Priority: P1)

**Goal**: The registry read facade exposes registered connectors uniformly; a new connector needs no source change.

**Independent Test**: Register a connector via `009`'s repo; `ConnectorRegistryReader.list_active()` includes it (archived excluded); `get()` returns the full record; data is identical regardless of caller.

### Implementation for User Story 2

- [ ] T010 [US2] Implement `src/harness/connector/registry.py`: `ConnectorRegistryReader(session)` with `list_active() -> list[ConnectorListEntry]` (excludes archived) and `get(connector_id)` (full `009` record); `ConnectorListEntry` frozen dataclass `(connector_id, display_name, description, expects_per_row_password)` (FR-009-011; R6)
- [ ] T011 [US2] Add `ConnectorRegistryReader` + `ConnectorListEntry` to `src/harness/connector/__init__.py` exports

### Tests for User Story 2

- [ ] T012 [P] [US2] `tests/unit/connector/test_registry_read.py`: `list_active` excludes archived + returns the minimal tuple; `get` returns full record; identical data for any caller (SC-003); FR-012 extensibility (register-then-list with no code change)

**Checkpoint**: Registry read surface usable by the wizard/orchestrator.

---

## Phase 5: User Story 3 — Protect stored credentials (Priority: P2)

**Goal**: Auth headers are built from just-in-time-decrypted credentials; decrypt failure is categorized; plaintext never leaks into results/logs. (At-rest encryption itself is reused from `009`.)

**Independent Test**: The 4 auth modes build the right header; a `bearer` registration's credential decrypts to the correct header; a key mismatch → `connector_auth`; plaintext absent from `ConnectorResult`.

### Tests for User Story 3

- [ ] T013 [P] [US3] `tests/unit/connector/test_auth.py`: `none` → `{}`; `bearer`/`api-key-header`/`basic` headers correct (base64 for basic); unknown mode → `ValueError` (FR-007a-d/FR-008)
- [ ] T014 [US3] `tests/unit/connector/test_client.py` (same file): auth header built from a decrypted `bearer` descriptor; decrypt failure → `ConnectorResult` with `error_stage="connector_auth"` and no request sent (FR-015/FR-016); credential plaintext not present in `ConnectorResult.error_details` (SC-004 spirit)

**Checkpoint**: Credential handling is correct and leak-free at the client boundary.

---

## Phase 6: User Story 4 — Bundled mock connector service (Priority: P2)

**Goal**: A stdlib mock connector ships, runs with zero external setup, emits a conformant contract, and supports error modes — enabling real end-to-end tests.

**Independent Test**: Launch the mock on a free port; a dispatched row gets a contract-valid response with `connectorId="mock"`; `--mode` produces non-2xx / non-conformant / slow behavior.

### Implementation for User Story 4

- [ ] T015 [US4] Implement `src/harness/connector/mock.py`: `ThreadingHTTPServer` + handler binding `127.0.0.1`; modes `ok` (default, conformant contract reflecting the utterance, `connectorId="mock"`) / `nonconformant` / `status500` / `slow` via `--mode`/`HARNESS_MOCK_MODE`; `__main__` entry (FR-018-022; R2)
- [ ] T016 [US4] Implement `src/harness/cli/connector.py`: `harness mock-connector [--port] [--mode]`; register the command on the `harness` group in `src/harness/cli/__init__.py` (FR-018)

### Tests for User Story 4

- [ ] T017 [P] [US4] `tests/integration/test_mock_service.py`: mock emits a body that passes `validate_contract` with `connectorId="mock"` (FR-019); each `--mode` yields the expected status/body; runs with no external setup (FR-020-022; SC-011)
- [ ] T018 [US4] `tests/integration/test_connector_e2e.py`: launch mock on an ephemeral port; dispatch 3 rows → all `ok` + valid contract, one request per row (SC-001/006); register via `009` repo + list via `ConnectorRegistryReader` + run (SC-002); `--mode` runs map to the right `errorStage` (SC-008/009/010)

**Checkpoint**: Real end-to-end works; MVP demoable (US1 client + US4 mock).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T019 [P] `python -m ruff check src tests --fix`; resolve findings
- [ ] T020 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 127 tests still pass + adequate `connector/` coverage
- [ ] T021 [P] Execute `specs/007-connector-framework/quickstart.md` end-to-end; file discrepancies
- [ ] T022 [P] Verify the plan's FR→File and SC matrices; confirm the `CLAUDE.md` marker points at the `007` plan

---

## Dependencies & Execution Order

- **Setup** → no deps. **Foundational** → depends on Setup; blocks all stories (delivers `dispatch_utterance`).
- **US1 (P3)** → test-only over the foundational client (MockTransport). MVP logic.
- **US2 (P4)** → adds `registry.py`; independent of US1.
- **US3 (P5)** → test-only over the foundational auth/client; `auth.py` already built in T005.
- **US4 (P6)** → adds the mock + CLI; the real end-to-end (T018) needs US4's mock **and** the US1 client. US2's `ConnectorRegistryReader` is used by T018's SC-002 check.
- **Polish** → after targeted stories.

### Critical path
Setup → Foundational → US1 (unit MVP) → US4 (mock ⇒ real e2e) → US2/US3 → Polish. (US2/US3 can interleave once Foundational is done.)

### Parallel opportunities
- Foundational: T004 ‖ T005 (distinct files); T006 depends on both; T007 after.
- Tests in **distinct** files are [P]: `test_auth.py` (T013), `test_registry_read.py` (T012), `test_mock_service.py` (T017). The three `test_client.py` tasks (T008/T009/T014) share one file → sequential.
- `client.py` is written once (T006); US1/US3 only *test* it.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 (MockTransport unit proof) → **then US4** to get the bundled mock → **STOP & VALIDATE** `test_connector_e2e.py` (a row really POSTed to a running connector returns a valid contract).

### Incremental delivery
US1 (dispatch) → US4 (mock + real e2e) → US2 (registry read) → US3 (credential safety) → Polish. Each ends green.

---

## Notes

- 007 is a **building block**: `dispatch_utterance` is one stateless call. The per-job loop + serialization (FR-005) belong to `012`; CRUD writes belong to `013`.
- Do NOT re-implement encryption — reuse `harness.persistence.encryption` (FR-013/014/016 already satisfied by `009`).
- `client.py` (T006) is the only file touched across foundational + stories; tests append to `test_client.py` sequentially. Commit after each task or logical group.
