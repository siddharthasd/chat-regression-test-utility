---
description: "Task list for Evaluation Agent Framework (Module 7)"
---

# Tasks: Evaluation Agent Framework (Module 7)

**Input**: Design documents from `specs/008-evaluation-agent-framework/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R9) ✅, data-model.md ✅, contracts/ (wire-protocol.md, client-api.md) ✅

**Tests**: INCLUDED (per-story Independent Tests + SC matrix).

**Branch base**: `008-evaluation-agent-framework` is on `foundation` (010+009+006). Sibling of `007` — reuses `009` (evaluator repo + encryption) but **cannot** import `harness.connector`; auth/decrypt is duplicated (dedup at integration). Paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no incomplete dependency.
- **[Story]**: US1–US5 on story phases; Setup/Foundational/Polish carry no label.

---

## Phase 1: Setup

- [ ] T001 Add `httpx>=0.27` to `[project].dependencies` in `pyproject.toml` (research R9)
- [ ] T002 Create scaffold: `src/harness/evaluator/__init__.py` and `tests/unit/evaluator/__init__.py`
- [ ] T003 Reinstall and confirm `import httpx`: `python -m pip install -e ".[dev]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: dispatch types, auth, the EvaluationResult validator, and the full HTTP client.

- [ ] T004 [P] Implement `src/harness/evaluator/result.py`: frozen `EvaluatorSnapshot`, `EvaluatorResult`, and `VERDICTS = {"pass","fail","warn"}` (data-model.md)
- [ ] T005 [P] Implement `src/harness/evaluator/auth.py`: `build_auth_headers(descriptor)` (4 modes, unknown → `ValueError`) + `_decrypt_descriptor` reusing `harness.persistence.encryption.decrypt_credential` (FR-007; R4/R5; duplicated from 007 — flag for dedup)
- [ ] T006 [P] Implement `src/harness/evaluator/validation.py`: `validate_evaluation_result(body, *, expected_utterance_id) -> list[str]` (FR-005b: 6 fields/types, utteranceId echo, verdict ∈ VERDICTS, scores-entry shape, ISO-8601 timestamp; agentId mismatch NOT a reject) + `compute_harness_annotations(scores, declared_dimensions) -> {"unexpected_score_dimensions": [...]}` (FR-005a)
- [ ] T007 Implement `src/harness/evaluator/client.py::dispatch_evaluation(snapshot, contract, *, client=None)`: decrypt (→ `evaluator_auth`), POST contract verbatim with `timeout` (no retry, no cache), map failures (`evaluator_transport`/`evaluator_response`), validate 2xx via `validate_evaluation_result` (→ `evaluator_result`), derive `harness_annotations` → `EvaluatorResult` (FR-001..006a). Depends on T004–T006.
- [ ] T008 Re-export `dispatch_evaluation`, `EvaluatorResult`, `EvaluatorSnapshot`, `validate_evaluation_result`, `compute_harness_annotations`, `build_auth_headers`, `VERDICTS` from `src/harness/evaluator/__init__.py`

**Checkpoint**: A contract can be dispatched (MockTransport) and the result validated/annotated/categorized.

---

## Phase 3: User Story 1 — Evaluate a row's contract end-to-end (Priority: P1) 🎯 MVP

**Goal**: Dispatch a contract, validate the EvaluationResult, derive annotations, categorize failures.

**Independent Test**: With a MockTransport returning a well-formed result, `dispatch_evaluation` returns `ok=True` with the result + annotations; body sent is the contract verbatim; bad results map to `evaluator_result`.

### Tests for User Story 1

- [ ] T009 [P] [US1] `tests/unit/evaluator/test_client.py`: success → `ok=True` + `evaluation_result` + `harness_annotations`; request body is the contract verbatim, no password (FR-002/017); exactly one request (SC-006)
- [ ] T010 [US1] `tests/unit/evaluator/test_client.py` (same file): errorStage map — non-2xx → `evaluator_response` (SC-008), invalid/bad-result body → `evaluator_result` (SC-007), timeout → `evaluator_transport` (SC-009), decrypt-fail → `evaluator_auth` (FR-016)
- [ ] T011 [P] [US1] `tests/unit/evaluator/test_validation.py`: FR-005b hard-rejects (missing field, wrong type, bad verdict, `utteranceId` mismatch, bad scores entry, bad timestamp); `evaluationAgentId` mismatch is NOT rejected (FR-003/004/005b)

**Checkpoint**: MVP evaluate-and-validate logic proven at the unit level.

---

## Phase 4: User Story 2 — Add an evaluator with zero core changes (Priority: P1)

**Goal**: The evaluator registry read facade exposes registered evaluators + their declared dimensions uniformly.

**Independent Test**: Register via `009`'s repo; `list_active()` includes it (archived excluded); `get()` full record; `get_declared_dimensions()` returns the ordered list.

### Implementation for User Story 2

- [ ] T012 [US2] Implement `src/harness/evaluator/registry.py`: `EvaluatorRegistryReader(session)` with `list_active() -> list[EvaluatorListEntry]` (excludes archived), `get(id)`, `get_declared_dimensions(id)`; `EvaluatorListEntry` frozen dataclass `(evaluation_agent_id, display_name, description, declared_scoring_dimensions)` (FR-008-013; R6)
- [ ] T013 [US2] Add `EvaluatorRegistryReader` + `EvaluatorListEntry` to `src/harness/evaluator/__init__.py`

### Tests for User Story 2

- [ ] T014 [P] [US2] `tests/unit/evaluator/test_registry_read.py`: `list_active` excludes archived + minimal tuple; `get` full record; `get_declared_dimensions` ordered (SC-011); identical data any caller (SC-003); register-then-list extensibility (FR-011)

**Checkpoint**: Registry read surface (incl. dimensions) usable.

---

## Phase 5: User Story 3 — Declared dimensions + unexpected-dimension annotation (Priority: P2)

**Goal**: harness derives `unexpected_score_dimensions` without rejecting; declared dimensions retrievable for ordering.

**Independent Test**: A result emitting a `parameter_name` outside the declared list is persisted with `harnessAnnotations.unexpected_score_dimensions: [name]`, not rejected.

### Tests for User Story 3

- [ ] T015 [P] [US3] `tests/unit/evaluator/test_validation.py` (same file as T011): `compute_harness_annotations` lists unexpected names (first-seen order), empty when aligned (FR-005/005a); a result with an out-of-declared name validates (soft warning, not reject)

**Checkpoint**: Dimension-drift is annotated, never rejected.

---

## Phase 6: User Story 5 — Bundled mock evaluator service (Priority: P2)

**Goal**: A stdlib mock evaluator emits well-formed, randomized results; supports error modes; runs with zero setup.

**Independent Test**: Launch the mock; a dispatched contract gets a valid `EvaluationResult` over the configured dimensions with `evaluationAgentId="mock-evaluator"`; `--mode` produces error behaviors.

### Implementation for User Story 5

- [ ] T016 [US5] Implement `src/harness/evaluator/mock.py`: `ThreadingHTTPServer` + handler; echoes `utteranceId`; randomized `evaluationScores` over `--dimensions`/`HARNESS_MOCK_DIMENSIONS`, random `evaluationVerdict ∈ VERDICTS`, `metadata={"mock": true}`; modes `ok`/`nonconformant`/`status500`/`slow`/`unexpected_dims` via `--mode`/`HARNESS_MOCK_MODE`; `__main__` (FR-022-027; R2)
- [ ] T017 [US5] Implement `src/harness/cli/evaluator.py`: `harness mock-evaluator [--port] [--mode] [--dimensions]`; register on the `harness` group in `src/harness/cli/__init__.py` (FR-022)

### Tests for User Story 5

- [ ] T018 [P] [US5] `tests/integration/test_mock_evaluator.py`: mock emits a result that passes `validate_evaluation_result` with `evaluationAgentId="mock-evaluator"` (FR-023); modes yield expected status/body; zero external setup (FR-026; SC-012)

**Checkpoint**: Real evaluator self-test available.

---

## Phase 7: User Story 4 — Non-determinism guarantee (Priority: P2)

**Goal**: No caching/dedup between orchestrator and evaluator call; identical input may yield different output.

**Independent Test**: Dispatch the same contract twice → two POSTs; the two results differ in verdict/scores/reasoning.

### Tests for User Story 4

- [ ] T019 [US4] `tests/integration/test_evaluator_e2e.py`: launch mock; dispatch a contract → `ok` + valid result (SC-001); register via `009` repo + run (SC-002); `--mode` runs → right `errorStage` (SC-007/008/009)
- [ ] T020 [US4] `tests/integration/test_evaluator_e2e.py` (same file): same contract dispatched twice → two POSTs (SC-006) and results differ in ≥1 field (SC-005); assert no cache/memo layer (FR-018-020)

**Checkpoint**: Real end-to-end works; non-determinism preserved.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T021 [P] `python -m ruff check src tests --fix`; resolve findings
- [ ] T022 `python -m pytest --cov=harness --cov-report=term-missing`; confirm the foundation's 127 still pass + adequate `evaluator/` coverage
- [ ] T023 [P] Execute `specs/008-evaluation-agent-framework/quickstart.md`; file discrepancies
- [ ] T024 [P] Verify FR→File and SC matrices; confirm `CLAUDE.md` marker → `008` plan

---

## Dependencies & Execution Order

- **Setup** → no deps. **Foundational** → blocks all stories (delivers `dispatch_evaluation` + validator).
- **US1 (P3)** → test-only over the foundational client/validator (MockTransport). MVP.
- **US2 (P4)** → adds `registry.py`; independent.
- **US3 (P5)** → test-only over the foundational `compute_harness_annotations`.
- **US5 (P6)** → adds the mock + CLI (real end-to-end infra).
- **US4 (P7)** → needs US5's mock for the real-server non-determinism/e2e tests.
- **Polish** → after targeted stories.

### Critical path
Setup → Foundational → US1 → US5 (mock) → US4 (e2e) → US2/US3 → Polish. (US2/US3 interleave once Foundational is done.)

### Parallel opportunities
- Foundational: T004 ‖ T005 ‖ T006 (distinct files); T007 depends on all; T008 after.
- Distinct test files are [P]: `test_validation.py`, `test_registry_read.py`, `test_mock_evaluator.py`. `test_client.py` (T009/T010) and `test_evaluator_e2e.py` (T019/T020) each share one file → sequential within.

---

## Implementation Strategy

### MVP
Setup → Foundational → US1 (MockTransport proof) → US5 (mock) → US4 e2e → **STOP & VALIDATE** a real contract dispatched to a running evaluator returns a valid, non-deterministic result.

### Incremental delivery
US1 → US5 (mock) → US4 (non-determinism) → US2 (registry) → US3 (annotations) → Polish.

---

## Notes

- 008 is the per-row dispatch building block (`dispatch_evaluation`); the job loop + serialization (FR-021) and persistence belong to `012`/`009`; CRUD writes belong to `014`.
- Reuse `harness.persistence.encryption` — do NOT add crypto. EvaluationResult validation is NEW here (not `006`'s `validate_contract`).
- `auth.py` duplicates `007`'s — extract a shared helper when `007`+`008` integrate. `client.py` (T007) and the shared test files are the only multi-task files; commit after each task/group.
