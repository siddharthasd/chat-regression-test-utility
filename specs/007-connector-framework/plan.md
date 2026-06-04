# Implementation Plan: Connector Framework (Module 4)

**Branch**: `007-connector-framework` | **Date**: 2026-06-04 | **Spec**: `specs/007-connector-framework/spec.md`

**Input**: Feature specification from `specs/007-connector-framework/spec.md`

## Summary

`007` defines the **connector wire protocol** and the harness's **generic HTTP client** for talking to remote chatbot connector services, plus the registry **read** surface, just-in-time credential decryption, and a **bundled mock connector service**. Per row, the harness issues one stateless `POST {testId, utteranceText, password?}` to the snapshotted endpoint, builds the auth header for one of four modes (`none`/`bearer`/`api-key-header`/`basic`), enforces the per-row timeout, and maps every failure onto the canonical `errorStage` enum (`connector_transport` / `connector_response` / `connector_normalization` / `connector_auth`). A 2xx body is validated against the Standard Evaluation Contract (Module 6) before being handed onward.

This module is a thin building block consumed by the orchestrator (`012`): it provides the per-row dispatch function, not the job loop. It **reuses the foundation** wholesale — `ConnectorRegistration` + `get_active`/`get`/`get_auth_descriptor_decrypted` from `009`, the Fernet credential encryption from `009` (FR-013/014/016 are already satisfied there — `007` *consumes* it, it does not re-introduce it), and `validate_contract` from `006`. It adds one runtime dependency: an HTTP client (`httpx`).

## Technical Context

**Language/Version**: Python 3.11+ (inherited via `foundation`).

**Primary Dependencies** (new in this spec):
- `httpx>=0.27` — sync HTTP client with first-class per-request `timeout=` and a `MockTransport` that lets the client be unit-tested without a live socket. The bundled mock service uses the **stdlib** `http.server` (no extra dep, trivially spawnable as a child process per FR-018).
- Reused from `foundation`: `harness.persistence` (`ConnectorRegistrationRepository`, `encryption.decrypt_credential`), `harness.contract` (`validate_contract`).

**Storage**: None new. The registry is backed by `009`'s `connector_registration` table; `007` only reads it. Execution-time config comes from the **Job snapshot** (parent FR-023), not the live registry.

**Testing**: `pytest`. Client paths driven via `httpx.MockTransport`; the mock service exercised over a real localhost port for end-to-end tests.

**Target Platform**: Windows + macOS + Linux. The mock binds `127.0.0.1:<free-port>`.

**Performance Goals**: One HTTP request per row; serial within a job (FR-005). No retries (FR-004). Timeout honored locally.

**Constraints**: At most one connector call in flight per job (FR-005); harness never retries (parent FR-025); decrypted credentials live only for the duration of one request and never reach logs/UI/export (FR-015).

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as `010`/`009`/`006`).

## Project Structure

### Documentation (this feature)

```text
specs/007-connector-framework/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R9)
├── data-model.md        # Phase 1 — wire protocol, ConnectorResult, auth/error mapping
├── quickstart.md        # Phase 1 — end-to-end against the bundled mock
├── contracts/
│   ├── wire-protocol.md           # request/response HTTP contract
│   └── client-api.md              # dispatch_utterance() / ConnectorResult / registry read
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
pyproject.toml                        # Add httpx to [project].dependencies
src/
└── harness/
    ├── connector/
    │   ├── __init__.py               # Re-exports: dispatch_utterance, ConnectorResult,
    │   │                             #             ConnectorRegistryReader, build_auth_headers
    │   ├── auth.py                   # build_auth_headers(descriptor) for the 4 modes (FR-007*)
    │   ├── client.py                 # dispatch_utterance(snapshot, row) -> ConnectorResult (FR-001..006)
    │   ├── result.py                 # ConnectorResult dataclass + ErrorStage helpers
    │   ├── registry.py               # ConnectorRegistryReader (list_active / get) over 009 repo (FR-009..011)
    │   └── mock.py                   # bundled mock connector service (stdlib http.server) (FR-018..022)
    └── cli/
        └── connector.py             # `harness mock-connector [--port] [--mode]` launcher (FR-018)

tests/
├── unit/
│   └── connector/
│       ├── __init__.py
│       ├── test_auth.py             # the 4 auth modes; none adds no header (FR-007a-d)
│       ├── test_client.py           # MockTransport: success, non-2xx, bad-json/non-conformant,
│       │                            # timeout, decrypt-fail → errorStage mapping (FR-004/006)
│       └── test_registry_read.py    # list_active excludes archived; get-by-id full record (FR-009-011)
└── integration/
    ├── test_mock_service.py         # mock emits conformant contract; parameterized error modes (FR-018-022)
    └── test_connector_e2e.py        # launch mock on a port, dispatch rows, body validates (SC-001/006)
```

**Structure Decision**: `src/harness/connector/` sub-package. The registry read API is a thin facade over `009`'s `ConnectorRegistrationRepository` (no new persistence). The mock service is stdlib-only so it spawns as a child process with no dependency surface (FR-021).

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001` (wire protocol, single-shot) | `connector/client.py` + contracts/wire-protocol.md | `integration/test_connector_e2e.py` |
| `FR-002` (POST body; password iff expectsPerRowPassword) | `connector/client.py::_build_body` | `unit/connector/test_client.py::test_body_*` |
| `FR-003` (2xx JSON validates vs contract) | `connector/client.py` (calls `validate_contract`) | `test_client.py::test_response_validated` |
| `FR-004` (timeout, no retry) | `connector/client.py` (httpx `timeout=`) | `test_client.py::test_timeout_*` |
| `FR-005` (serial per job) | (orchestration property — enforced by `012`) | noted; `007` exposes a sync single-call fn |
| `FR-006` (errorStage mapping) | `connector/result.py` + `client.py` | `test_client.py::test_error_stage_*` |
| `FR-007`/`007a-d` (4 auth modes) | `connector/auth.py` | `unit/connector/test_auth.py` |
| `FR-008` (no other modes) | `connector/auth.py` (raises on unknown) | `test_auth.py::test_unknown_mode` |
| `FR-009`–`FR-011` (registry read API) | `connector/registry.py` | `unit/connector/test_registry_read.py` |
| `FR-012` (zero-core-change extensibility) | (architectural) | `integration/test_connector_e2e.py` (register+run mock) |
| `FR-013`/`014`/`016` (credential encryption) | **reused from `009`** (`encryption` + repo) | covered by `009`; `test_client.py::test_decrypt_fail` |
| `FR-015` (plaintext in-memory only, JIT) | `connector/client.py` (decrypt → header → drop) | `test_client.py::test_auth_header_built` |
| `FR-017` (per-row password not encrypted) | `connector/client.py` (forwarded plaintext in body, never stored) | `test_client.py::test_body_password` |
| `FR-018`–`FR-022` (bundled mock service) | `connector/mock.py` + `cli/connector.py` | `integration/test_mock_service.py` |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `integration/test_connector_e2e.py::test_end_to_end_contract_valid` |
| `SC-002` | `integration/test_connector_e2e.py::test_register_and_run_mock_no_core_change` |
| `SC-003` | `unit/connector/test_registry_read.py::test_identical_data_all_callers` |
| `SC-004` | covered by `009` encryption tests + `test_client.py::test_no_plaintext_in_logs` |
| `SC-005` | covered by `009` `test_encryption.py::test_key_missing_or_wrong_raises` |
| `SC-006` | `test_connector_e2e.py::test_one_request_per_row` |
| `SC-007` | `test_connector_e2e.py::test_concurrent_jobs_independent` |
| `SC-008` | `test_client.py::test_non_2xx_is_connector_response` |
| `SC-009` | `test_client.py::test_nonconformant_is_connector_normalization` |
| `SC-010` | `test_client.py::test_timeout_is_connector_transport` |
| `SC-011` | `integration/test_mock_service.py::test_mock_zero_external_setup` |

## Foundation Note

`007` is built on the **`foundation`** branch (010 + 009 + 006 integrated, 127 tests green). It is the first module to depend on all three foundations simultaneously: registry + encryption from `009`, contract validation from `006`, identity/CLI scaffolding from `010`. No re-graft needed — `foundation` already carries them.

## Complexity Tracking

| Element | Justification |
|---|---|
| `httpx` dependency | Per-request timeout + `MockTransport` for socket-free client tests; stdlib `urllib` lacks ergonomic timeouts and is painful to mock |
| Stdlib-only mock service | FR-021 requires the mock to spawn in tests with no external dep / network; `http.server` keeps the mock dependency-free and child-process-spawnable |
| Registry read facade over `009` repo | FR-009–011 define a stable read surface distinct from `013`'s write surface, though both sit on the one `009` table |
| Reusing `009` encryption (not re-implementing) | FR-013/014/016 are already realized in `009`; duplicating Fernet logic would risk divergence (two key-handling paths) |
