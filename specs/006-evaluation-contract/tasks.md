---
description: "Task list for Standard Evaluation Contract (Module 6)"
---

# Tasks: Standard Evaluation Contract (Module 6)

**Input**: Design documents from `specs/006-evaluation-contract/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md (R1–R10) ✅, data-model.md ✅, contracts/ (validation-api.md, cli-contract.md) ✅

**Tests**: INCLUDED. The spec defines an "Independent Test" per user story plus an SC→test matrix in plan.md, so test tasks are first-class.

**Branch base**: `006-evaluation-contract` is fast-forwarded onto `012` (canonical specs). The project foundation (`pyproject.toml`, `src/harness/` skeleton, `pytest`/`ruff`) lives on `010` and must be grafted before coding — same as `009` (see plan's Foundation Note). Paths below are relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different files, no dependency on an incomplete task → parallelizable.
- **[Story]**: US1–US4 on story phases; Setup/Foundational/Polish carry no story label.

---

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 Graft the `010` foundation if not already present (`git checkout 010-tester-identity -- pyproject.toml .python-version .gitignore src tests`), then add `jsonschema>=4.21` to `[project].dependencies` and ensure `*.json` under `src/harness/contract/schemas/` ships as package data (`[tool.setuptools] include-package-data` or `package-data`) in `pyproject.toml` (research R10)
- [X] T002 Create the contract package scaffold: `src/harness/contract/__init__.py` and the `src/harness/contract/schemas/` directory
- [X] T003 Reinstall editable and confirm `import jsonschema` resolves: `python -m pip install -e ".[dev]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The bundled schema, result types, schema loader, and the core structural validator that every user story builds on.

**⚠️ CRITICAL**: No user-story phase can begin until this phase is complete.

- [X] T004 Author the bundled JSON Schema `src/harness/contract/schemas/standard_evaluation_contract.schema.json` (Draft 2020-12): all 8 required top-level fields (FR-002), the `chatbotResponse` sub-object (FR-003), `conversationContext` as `["object","null"]`, `timestamp` `format: date-time` (FR-013), `contractVersion` `pattern: ^[0-9]+$`, `rawPayload` unconstrained (`true`), `additionalProperties` left open at every level (FR-005), and per-field `description` annotations (FR-014)
- [X] T005 [P] Implement `src/harness/contract/violations.py`: `ViolationKind` StrEnum (`missing`/`wrong_type`/`bad_format`/`version_out_of_range`/`forbidden_field`/`schema`), frozen `Violation` and `ValidationResult` dataclasses (per contracts/validation-api.md)
- [X] T006 [P] Implement `src/harness/contract/schema.py`: `load_schema()` via `importlib.resources`, `BUNDLED_CONTRACT_VERSION: int = 1`, and a cached `Draft202012Validator` built with a `FormatChecker` so `date-time` is asserted (research R2/R5/R8)
- [X] T007 Implement the structural core of `validate_contract()` in `src/harness/contract/validation.py`: run `validator.iter_errors(instance)`, map each `ValidationError` to a `Violation` (json_path → `field_path`; keyword → `ViolationKind`; `validator_value`/`instance` → expected/observed), return a deterministically-ordered `ValidationResult`; never raise on arbitrary input (FR-002/003/008/011/013)
- [X] T008 Re-export `validate_contract`, `ValidationResult`, `Violation`, `ViolationKind`, `BUNDLED_CONTRACT_VERSION` from `src/harness/contract/__init__.py`
- [X] T009 [P] `tests/unit/contract/__init__.py` + `tests/unit/contract/test_schema.py`: schema loads; the required/optional field sets match FR-002/FR-003; every field carries a `description` (FR-014); `BUNDLED_CONTRACT_VERSION` equals the schema's own declared version (no drift, R8)

**Checkpoint**: Structural validation works end-to-end for conforming and structurally-invalid instances.

---

## Phase 3: User Story 1 — A conforming instance passes and is forwardable (Priority: P1) 🎯 MVP

**Goal**: A schema-conformant contract instance validates cleanly and is reachable both as `validate_contract()` and via the authoring CLI.

**Independent Test**: A hand-rolled conforming instance returns `valid=True` with no violations; required field values are preserved; `harness contract validate good.json` exits 0.

### Implementation for User Story 1

- [X] T010 [US1] Implement the `harness contract validate <file> [--json]` CLI in `src/harness/cli/contract.py` (reads JSON, calls `validate_contract`, human + `--json` output, exit codes 0/1/2 per contracts/cli-contract.md, FR-010)
- [X] T011 [US1] Register the `contract` command group on the `harness` Click group in `src/harness/cli/__init__.py`

### Tests for User Story 1

- [X] T012 [P] [US1] `tests/unit/contract/test_validation.py::test_conformant_instance_passes` — a fully-conforming instance yields `valid=True`, `violations==[]` (SC-001)
- [X] T013 [P] [US1] `tests/unit/contract/test_validation.py::test_required_values_preserved` — required field values are unchanged through validation (round-trip, SC-001)
- [X] T014 [US1] `tests/integration/test_contract_cli.py::test_validate_conforming_exit_zero` — CLI on a conforming file prints `VALID` and exits 0 (SC-008)

**Checkpoint**: MVP — conforming instances validate and the authoring CLI works.

---

## Phase 4: User Story 2 — Reject a non-conforming instance at the boundary (Priority: P1)

**Goal**: Missing/wrong-type/bad-format fields, a `password` key anywhere, or a `contractVersion` ahead of the bundled version are all rejected with actionable, field-named detail.

**Independent Test**: Instances that (a) omit `utteranceId`, (b) carry a non-ISO `timestamp`, (c) type `normalizedText` as a number, (d) contain a `password` key, (e) declare `contractVersion` "2" — each returns `valid=False` with a violation naming the offending field/version.

### Implementation for User Story 2

- [X] T015 [US2] Add `_scan_for_password(instance)` recursive scan to `src/harness/contract/validation.py` and wire it into `validate_contract` — any `password` key at any depth → `FORBIDDEN_FIELD` violation with dotted/indexed path (FR-004)
- [X] T016 [US2] Add the numeric `contractVersion` gate to `validate_contract` in `src/harness/contract/validation.py`: parse as int (FR-016), accept `<=` bundled, reject `>` bundled with a `VERSION_OUT_OF_RANGE` violation naming both versions + "update the harness" remediation (FR-015)

### Tests for User Story 2

- [X] T017 [P] [US2] `tests/unit/contract/test_validation.py`: `test_missing_field_named` (SC-002), `test_type_mismatch_named` (SC-003), `test_timestamp_format` (FR-013), `test_password_forbidden_nested` (FR-004) — each asserts the violation `field_path`/`kind`/detail
- [X] T018 [P] [US2] `tests/integration/test_contract_cli.py::test_validate_nonconforming_exit_one` — CLI on a malformed file prints `INVALID` with violations and exits 1; bad JSON / missing file exits 2

**Checkpoint**: Every rejection path produces actionable, field-named detail; the malformed instance never passes.

---

## Phase 5: User Story 3 — Add a new optional field without breaking consumers (Priority: P2)

**Goal**: Unknown extension fields (top-level or nested) validate as conforming and don't change `contractVersion`.

**Independent Test**: An instance with `chatbotResponse.metadata.toolCallCount` (and an unknown top-level field) validates `True`; absence of new fields on older instances also validates.

### Tests for User Story 3

- [X] T019 [P] [US3] `tests/unit/contract/test_validation.py::test_unknown_fields_ok` — instance with extra top-level + nested unknown fields validates `True` (FR-005, SC-005)
- [X] T020 [P] [US3] `tests/unit/contract/test_validation.py::test_empty_agentchain_and_metadata_ok` — `agentChain: []`, `metadata: {}`, and `conversationContext: null` all validate (spec edge cases)

**Checkpoint**: Extensibility property holds; no code change needed (schema is open by design from T004).

---

## Phase 6: User Story 4 — Reject changes that would silently break consumers (Priority: P3)

**Goal**: Numeric (not lexicographic) version comparison; the additive-vs-breaking versioning policy is encoded as a checkable dev-time test.

**Independent Test**: `"10"` compares greater than `"2"`; an additive field doesn't bump the version; a breaking change requires a bump.

### Tests for User Story 4

- [X] T021 [P] [US4] `tests/unit/contract/test_versioning.py::test_numeric_not_lexicographic` — an instance at `"10"` vs a bundled `"2"` scenario compares numerically (FR-016)
- [X] T022 [P] [US4] `tests/unit/contract/test_versioning.py::test_version_greater_rejected` — `contractVersion` greater than bundled → `VERSION_OUT_OF_RANGE` naming both versions (SC-004)
- [X] T023 [P] [US4] `tests/unit/contract/test_versioning.py::test_determinism` — two calls on the same input yield equal `ValidationResult` (order/content/count) (FR-011, SC-009)
- [X] T024 [P] [US4] `tests/unit/contract/test_versioning.py::test_breaking_change_policy` — encode FR-007's rule set (removed/renamed/retyped/newly-required field ⇒ must bump) as an assertion over a small breaking-change detector helper; `test_additive_no_bump` for FR-006 (SC-006/SC-007)

**Checkpoint**: Versioning policy is machine-checkable; numeric semantics verified.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T025 [P] `python -m ruff check src tests --fix`; resolve findings
- [X] T026 `python -m pytest --cov=harness --cov-report=term-missing`; confirm no regression in grafted `010`/`009` tests and adequate `contract/` coverage
- [X] T027 Verify the bundled `*.json` schema actually ships with the installed package (import + `load_schema()` from an installed location, not just the source tree) — guards the R10 package-data config
- [X] T028 [P] Execute `specs/006-evaluation-contract/quickstart.md` end-to-end; file any discrepancy as a follow-up
- [X] T029 [P] Verify the plan's FR→File and SC matrices: every FR has an implementation file and a passing test; confirm `CLAUDE.md` marker still points at the `006` plan

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → no deps.
- **Foundational (P2)** → depends on Setup; **blocks all stories**. Delivers the schema + structural validator, which already satisfies US1's "passes" and US3's "unknown ok" behavior.
- **US1 (P3)** → depends on Foundational; adds the CLI + verifying tests. MVP.
- **US2 (P4)** → depends on Foundational; **extends `validation.py`** (T015/T016 edit the file from T007 — sequential).
- **US3 (P5)** → depends on Foundational; **test-only** (schema is already open).
- **US4 (P6)** → depends on Foundational + the version gate (T016, built in US2); the gate tests (T022) need T016. The policy/determinism tests are otherwise independent.
- **Polish (P7)** → depends on all targeted stories.

### Critical path

Setup → Foundational → US1 (MVP) → US2 → (US3, US4) → Polish.

### Within stories

Schema → result types → validator core → CLI/guards → tests.

---

## Parallel Opportunities

- **Foundational**: T005 (violations) ‖ T006 (schema loader) ‖ T009 (schema tests) — distinct files; T007 (validation core) depends on T005/T006; T004 (schema JSON) gates T006/T007.
- **US1**: T012 ‖ T013 (same test file, distinct functions — effectively parallel authoring); T010/T011 are sequential CLI wiring.
- **US2**: T015 and T016 both edit `validation.py` → sequential; tests T017 ‖ T018.
- **US3 / US4**: all test tasks are [P] (distinct test functions/files), except T022 which needs T016.
- **Cross-story**: once Foundational is done, US3 (test-only) can be written in parallel with US1/US2.

### Parallel example — Foundational

```text
Task: "Implement violations.py"        (T005)
Task: "Implement schema.py loader"     (T006)   # after T004 schema JSON exists
Task: "Write test_schema.py"           (T009)
```

---

## Implementation Strategy

### MVP first (US1)

Setup → Foundational → US1 → **STOP & VALIDATE**: `test_conformant_instance_passes` + `harness contract validate good.json`. A working, demoable contract validator.

### Incremental delivery

US1 (accept + CLI) → US2 (reject paths: password + version + detail) → US3 (extensibility) → US4 (versioning policy) → Polish. Each phase ends green without breaking prior phases.

---

## Notes

- `[P]` = different files / independent. Tasks editing `src/harness/contract/validation.py` (T007, T015, T016) are intentionally sequential.
- This module is pure validation — **no database, no network** (FR-011 determinism). The harness boundary that *calls* `validate_contract` per row lives in `012` (SC-010); it is out of scope here.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
