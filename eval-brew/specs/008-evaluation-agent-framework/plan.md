# Implementation Plan: Evaluation Agent Framework (Module 7)

**Branch**: `008-evaluation-agent-framework` | **Date**: 2026-06-04 | **Spec**: `specs/008-evaluation-agent-framework/spec.md`

**Input**: Feature specification from `specs/008-evaluation-agent-framework/spec.md`

## Summary

`008` is the **consumer-side twin of `007`**: the evaluator wire protocol + a generic HTTP client that POSTs a Standard Evaluation Contract instance to a remote evaluator service and validates the returned `EvaluationResult`. Per row, the harness issues one stateless `POST <contract>` to the snapshotted evaluator endpoint, builds the auth header (same four modes as `007`), enforces the per-row timeout, and maps failures onto the evaluator error stages (`evaluator_transport` / `evaluator_response` / `evaluator_result` / `evaluator_auth`). On a 2xx it **hard-validates** the six EvaluationResult fields (FR-005b: required fields/types, `utteranceId` echo, `verdict ∈ {pass,fail,warn}`, scores-entry shape, ISO-8601 timestamp) and **derives** `harnessAnnotations.unexpected_score_dimensions` by diffing emitted `parameter_name`s against the registration's declared dimensions. It guarantees **no caching/dedup** (FR-018) and ships a **bundled mock evaluator** that emits randomized-but-well-formed results.

It reuses the foundation: `EvaluationAgentRegistration` + `get_active`/`get`/`get_declared_dimensions` from `009`, the Fernet credential encryption from `009`. It does **not** validate via `006` (that's the connector→evaluator *input* shape; the EvaluationResult is a distinct shape defined here). Adds one runtime dependency: `httpx`.

## Technical Context

**Language/Version**: Python 3.11+ (inherited via `foundation`).

**Primary Dependencies** (new in this spec):
- `httpx>=0.27` — sync client, per-request `timeout=`, `MockTransport` for socket-free tests (same choice as `007`). Bundled mock evaluator uses the **stdlib** `http.server` (no dep; child-process spawnable, FR-022/026).
- Reused from `foundation`: `harness.persistence` (`EvaluationAgentRegistrationRepository`, `encryption.decrypt_credential`).

**Storage**: None new. The evaluator registry is `009`'s `evaluation_agent_registration` table; `008` reads it. Execution-time config comes from the Job snapshot (parent FR-023).

**Testing**: `pytest`. Client + EvaluationResult-validation via `httpx.MockTransport`; the mock evaluator exercised over a real localhost port.

**Target Platform**: Windows + macOS + Linux. Mock binds `127.0.0.1:<free-port>`.

**Performance Goals**: One HTTP request per row; serial within a job (FR-021); no retries (FR-006); **never cached** (FR-018).

**Constraints**: No memoization/dedup between orchestrator and evaluator call (FR-018-020); decrypted credentials live only for one request (FR-015); the per-row CSV password is never forwarded to the evaluator (FR-017 — body is the contract only).

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as prior modules).

## Project Structure

### Documentation (this feature)

```text
specs/008-evaluation-agent-framework/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R9)
├── data-model.md        # Phase 1 — wire protocol, EvaluationResult shape, validation, annotations
├── quickstart.md        # Phase 1 — end-to-end against the bundled mock evaluator
├── contracts/
│   ├── wire-protocol.md           # request (contract) / response (EvaluationResult) HTTP contract
│   └── client-api.md              # dispatch_evaluation() / validate_evaluation_result() / registry read
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
pyproject.toml                        # Add httpx to [project].dependencies
src/
└── harness/
    ├── evaluator/
    │   ├── __init__.py               # Re-exports: dispatch_evaluation, EvaluatorResult,
    │   │                             #             validate_evaluation_result, EvaluatorRegistryReader
    │   ├── auth.py                   # build_auth_headers + _decrypt_descriptor (4 modes; FR-007)
    │   ├── validation.py             # validate_evaluation_result() + compute_harness_annotations() (FR-003/004/005/005a/005b)
    │   ├── client.py                 # dispatch_evaluation(snapshot, contract) -> EvaluatorResult (FR-001..006a)
    │   ├── result.py                 # EvaluatorSnapshot, EvaluatorResult dataclasses + VERDICTS
    │   ├── registry.py               # EvaluatorRegistryReader (list_active/get/get_declared_dimensions) (FR-008..013)
    │   └── mock.py                   # bundled mock evaluator service (stdlib http.server) (FR-022..027)
    └── cli/
        └── evaluator.py             # `harness mock-evaluator [--port] [--mode] [--dimensions]` (FR-022)

tests/
├── unit/
│   └── evaluator/
│       ├── __init__.py
│       ├── test_auth.py             # 4 auth modes (FR-007)
│       ├── test_validation.py       # FR-005b hard-rejects + FR-005a annotations + verdict/utteranceId checks
│       ├── test_client.py           # MockTransport: success, non-2xx, bad-result, timeout, decrypt-fail → errorStage
│       └── test_registry_read.py    # list_active/get/get_declared_dimensions (FR-008-011, SC-003/011)
└── integration/
    ├── test_mock_evaluator.py       # mock emits well-formed result; non-determinism; modes (FR-022-027, SC-012)
    └── test_evaluator_e2e.py        # launch mock, dispatch contract, validate; error modes (SC-001/005/007/008/009)
```

**Structure Decision**: `src/harness/evaluator/` sub-package, mirroring `007`'s `connector/`. The registry read API is a thin facade over `009`'s `EvaluationAgentRegistrationRepository`. The mock is stdlib-only.

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001`/`FR-002` (wire protocol; contract as body) | `evaluator/client.py` | `integration/test_evaluator_e2e.py` |
| `FR-003` (6 EvaluationResult fields) | `evaluator/validation.py` | `unit/evaluator/test_validation.py::test_required_fields` |
| `FR-004` (verdict enum) | `evaluator/validation.py` + `result.py::VERDICTS` | `test_validation.py::test_bad_verdict` |
| `FR-005` (scores entry shape) | `evaluator/validation.py` | `test_validation.py::test_bad_scores_entry` |
| `FR-005a` (harnessAnnotations.unexpected_score_dimensions) | `evaluator/validation.py::compute_harness_annotations` | `test_validation.py::test_unexpected_dimensions` |
| `FR-005b` (hard-reject → evaluator_result) | `evaluator/validation.py::validate_evaluation_result` | `test_validation.py::test_reject_*` |
| `FR-006`/`FR-006a` (timeout, no retry, errorStage map) | `evaluator/client.py` | `test_client.py::test_error_stage_*` |
| `FR-007` (4 auth modes) | `evaluator/auth.py` | `unit/evaluator/test_auth.py` |
| `FR-008`–`FR-013` (registry read incl. dimensions) | `evaluator/registry.py` | `unit/evaluator/test_registry_read.py` |
| `FR-014`/`FR-016` (credential encryption) | **reused from `009`** + `auth.py` decrypt | covered by `009`; `test_client.py::test_decrypt_fail` |
| `FR-015` (plaintext JIT only) | `evaluator/client.py` | `test_client.py::test_auth_header_built` |
| `FR-017` (no password to evaluator) | `evaluator/client.py` (body = contract only) | `test_client.py::test_body_is_contract` |
| `FR-018`–`FR-020` (no caching) | `evaluator/client.py` (no cache layer) | `test_evaluator_e2e.py::test_same_input_two_calls` |
| `FR-021` (serial per job) | (orchestration — `012`) | noted |
| `FR-022`–`FR-027` (bundled mock evaluator) | `evaluator/mock.py` + `cli/evaluator.py` | `integration/test_mock_evaluator.py` |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `integration/test_evaluator_e2e.py::test_end_to_end_result_valid` |
| `SC-002` | `test_evaluator_e2e.py::test_register_and_run_no_core_change` |
| `SC-003` | `unit/evaluator/test_registry_read.py::test_identical_data_all_callers` |
| `SC-004` | declared-order rendering is `004`/`005`'s concern; here `get_declared_dimensions` returns ordered list (`test_registry_read.py`) |
| `SC-005` | `test_evaluator_e2e.py::test_same_input_two_calls_differ` |
| `SC-006` | `test_evaluator_e2e.py::test_one_request_per_row` |
| `SC-007` | `test_validation.py` + `test_evaluator_e2e.py::test_malformed_is_evaluator_result` |
| `SC-008` | `test_client.py::test_non_2xx_is_evaluator_response` |
| `SC-009` | `test_client.py::test_timeout_is_evaluator_transport` |
| `SC-010` | (cross-job — orchestration; out of scope here) |
| `SC-011` | `test_registry_read.py::test_get_declared_dimensions` |
| `SC-012` | `integration/test_mock_evaluator.py::test_nondeterministic_and_zero_setup` |
| `SC-013` | covered by `009` encryption tests (same pattern as `007 SC-004`) |

## Foundation Note & Coherence

`008` is built on **`foundation`** (010+009+006), as a **sibling of `007`** (both branch off `foundation`; `007` is not a dependency). Consequences:
- `008` reuses `009`'s evaluator registry repo + encryption and adds `httpx` (same dep `007` added independently → a union at integration).
- The **4-mode auth-header + descriptor-decrypt logic is duplicated** from `007`'s `connector/auth.py` into `evaluator/auth.py`, because `008` cannot import `harness.connector` (sibling branch). This is intentional, isolated duplication; when `007` + `008` are folded into the next foundation rollup, extract a shared `harness`-level HTTP-auth helper and point both at it. Flagged in Complexity Tracking.
- The `errorStage` values used here (`evaluator_*`) are part of `009`'s canonical `ERROR_STAGES` set — verified present.

## Complexity Tracking

| Element | Justification |
|---|---|
| `httpx` dependency | Same rationale as `007` — per-request timeout + `MockTransport` for socket-free tests |
| Stdlib mock evaluator | FR-026 needs a dependency-free, child-spawnable mock with randomized output |
| Duplicated auth/decrypt vs `007` | `008` can't import `harness.connector` (sibling branch); duplication is small and isolated, to be deduped into a shared helper at `007`+`008` integration |
| New EvaluationResult validator (not `006`) | The evaluator *response* is a distinct shape from the connector→evaluator *contract*; FR-005b defines its own hard-reject rules |
