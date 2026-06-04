# Implementation Plan: Standard Evaluation Contract (Module 6)

**Branch**: `006-evaluation-contract` | **Date**: 2026-06-03 | **Spec**: `specs/006-evaluation-contract/spec.md`

**Input**: Feature specification from `specs/006-evaluation-contract/spec.md`

## Summary

`006` defines the **Standard Evaluation Contract** — the single versioned JSON wire format passed from connector services (producers) through the harness to evaluator services (consumers), and persisted as `EvaluationResult.normalizedContract` (`009 FR-003`). The deliverables are: (1) a bundled, versioned **JSON Schema (Draft 2020-12)** artifact naming every required/optional field and the additive-extensibility policy; (2) a **validation utility** (`validate_contract()`) that takes any JSON object and returns conformance + a structured per-field violation list; (3) a **runtime version gate** enforcing the bundled-schema accepted range with numeric `contractVersion` comparison; (4) a **`password`-forbidden-anywhere** check; and (5) a thin **CLI** (`harness contract validate`) exposing the same validation for connector/evaluator authors.

This spec brings `jsonschema` into the runtime dependency graph. It inherits the project-wide foundation (`src/harness/` package, `pyproject.toml`, `pytest` + `ruff`) established by Module 3 (`010`). It is pure validation logic — **no database access**; the harness boundary that *calls* this validation lives in the orchestrator (`012 FR-011` step 4).

## Technical Context

**Language/Version**: Python 3.11+ (inherited from `010`).

**Primary Dependencies** (new in this spec):
- `jsonschema>=4.21` — JSON Schema Draft 2020-12 validator with format-assertion support (`date-time` for `timestamp`, FR-013). 4.21+ ships the `Draft202012Validator` and a stable `iter_errors` surface.
- `importlib.resources` (stdlib) — load the bundled schema artifact from package data.

**Dev dependencies**: none beyond `010`'s baseline.

**Storage**: N/A. The schema is a static bundled artifact (`FR-015`: exactly one — the latest). This module performs no persistence; contract instances are persisted elsewhere by `009`.

**Testing**: `pytest`. Pure-function validation tests (hand-rolled conforming / non-conforming instances) + a CLI integration test.

**Target Platform**: Windows + macOS + Linux (validation is platform-agnostic, no I/O beyond reading the bundled schema).

**Performance Goals**: Validation < 5ms per contract instance at the 1,000-row design target; the compiled validator + schema are loaded once at import.

**Constraints**: Deterministic — identical input yields identical `valid` flag and violation list, no randomness or time-dependence (`FR-011`). No network access. `additionalProperties` permitted at every level (`FR-005`); `password` forbidden at every level (`FR-004`).

## Constitution Check

Unfilled template — GATE: PASS by vacuous quantification (same as `009`/`010`).

## Project Structure

### Documentation (this feature)

```text
specs/006-evaluation-contract/
├── plan.md              # This file
├── spec.md
├── research.md          # Phase 0 (R1–R10)
├── data-model.md        # Phase 1 — contract entities, field tables, version semantics
├── quickstart.md        # Phase 1 — end-to-end verification per US1–US4
├── contracts/
│   ├── validation-api.md          # validate_contract() / ValidationResult / Violation
│   └── cli-contract.md            # `harness contract validate` surface
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (not created by this plan)
```

### Source Code

```text
pyproject.toml                        # Add jsonschema to [project].dependencies
src/
└── harness/
    ├── contract/
    │   ├── __init__.py               # Re-exports: validate_contract, ValidationResult,
    │   │                             #             Violation, BUNDLED_CONTRACT_VERSION
    │   ├── schema.py                 # load_schema() via importlib.resources;
    │   │                             # BUNDLED_CONTRACT_VERSION single source of truth
    │   ├── validation.py            # validate_contract(); structural + version + password checks
    │   ├── violations.py            # Violation + ValidationResult dataclasses + ViolationKind
    │   └── schemas/
    │       └── standard_evaluation_contract.schema.json   # bundled Draft 2020-12 schema (FR-015)
    └── cli/
        └── contract.py              # `harness contract validate <file>` (FR-010 authoring surface)

tests/
├── unit/
│   └── contract/
│       ├── __init__.py
│       ├── test_schema.py           # schema loads; required/optional field set; version constant
│       ├── test_validation.py       # US1 valid, US2 invalid (missing/type/format/password), US3 extras
│       └── test_versioning.py       # numeric gate (FR-015/FR-016), determinism (FR-011), US4 policy
└── integration/
    └── test_contract_cli.py         # `harness contract validate` conforming + non-conforming exit codes
```

**Structure Decision**: `src/harness/contract/` sub-package. The bundled schema ships as package data under `contract/schemas/` and is loaded once. `cli/contract.py` registers a `contract` command group on the existing `harness` CLI (mirrors `cli/info.py`).

## FR → File Coverage Matrix

| FR | Implementation file | Verifying test |
|---|---|---|
| `FR-001` (single versioned schema artifact) | `contract/schemas/standard_evaluation_contract.schema.json` + `contract/schema.py` | `unit/contract/test_schema.py::test_schema_loads` |
| `FR-002` (required top-level fields) | schema `required` + `contract/schema.py` | `test_schema.py::test_required_fields` |
| `FR-003` (`chatbotResponse` sub-fields) | schema `chatbotResponse` definition | `test_schema.py::test_chatbot_response_fields` |
| `FR-004` (no `password` anywhere) | `contract/validation.py::_scan_for_password` | `test_validation.py::test_password_forbidden_*` |
| `FR-005` (extensibility / additionalProperties) | schema (`additionalProperties` left open) | `test_validation.py::test_unknown_fields_ok` |
| `FR-006` (additive never bumps) | (policy — schema design) | `test_versioning.py::test_additive_no_bump` |
| `FR-007` (breaking changes bump) | (policy — documented) | `test_versioning.py::test_breaking_change_policy` |
| `FR-008` (validate at boundary, every row) | `contract/validation.py::validate_contract` | `test_validation.py` (unit); enforced by `012` |
| `FR-009` (failure detail + `connector_normalization`) | `contract/violations.py` + `validation.py` | `test_validation.py::test_violation_detail_*` |
| `FR-010` (authoring-reachable validation) | `contract/validation.py` + `cli/contract.py` | `integration/test_contract_cli.py` |
| `FR-011` (deterministic) | `contract/validation.py` | `test_versioning.py::test_determinism` |
| `FR-012` (reserved — no content) | (confirmed absent) | verified by absence |
| `FR-013` (ISO-8601 timestamp) | schema `format: date-time` + format checker | `test_validation.py::test_timestamp_format` |
| `FR-014` (field descriptions) | schema `description` annotations | `test_schema.py::test_fields_documented` |
| `FR-015` (single bundled latest; numeric gate) | `contract/schema.py::BUNDLED_CONTRACT_VERSION` + `validation.py` version gate | `test_versioning.py::test_version_gate_*` |
| `FR-016` (numeric comparison) | `contract/validation.py` version parse | `test_versioning.py::test_numeric_not_lexicographic` |

## SC Verification Matrix

| SC | Verification path |
|---|---|
| `SC-001` | `test_validation.py::test_conformant_instance_passes` |
| `SC-002` | `test_validation.py::test_missing_field_named` |
| `SC-003` | `test_validation.py::test_type_mismatch_named` |
| `SC-004` | `test_versioning.py::test_version_greater_rejected` |
| `SC-005` | `test_validation.py::test_unknown_fields_ok` |
| `SC-006` | `test_versioning.py::test_additive_no_bump` |
| `SC-007` | `test_versioning.py::test_breaking_change_policy` |
| `SC-008` | `integration/test_contract_cli.py` + `test_validation.py` direct calls |
| `SC-009` | `test_versioning.py::test_determinism` |
| `SC-010` | (enforced in `012`'s per-row pipeline; here: `validate_contract` is the single gate fn) |

## Branch-Staleness & Foundation Note

`006`'s working branch has been fast-forwarded onto `012` (the canonical post-reshape spec set), so the spec and all cross-spec citations (`007 FR-002`/`FR-003`/`FR-006`, `008 FR-002`/`FR-003`, `009 FR-001a`/`FR-003`, `012 FR-011`/`FR-012`, `014`) resolve against canonical state. Like `009`, the **project foundation** (`pyproject.toml`, `src/harness/` skeleton, `pytest`/`ruff` config) lives only on the `010-tester-identity` branch; implementation will graft that foundation in the same way `009` did before coding begins.

## Complexity Tracking

| Element | Justification |
|---|---|
| `jsonschema` dependency | FR-001/FR-008 require schema-based structural validation with a full per-field violation list; hand-rolling a Draft 2020-12 validator is far costlier than the dep |
| In-code version gate (not pure schema) | FR-015/FR-016 require numeric `contractVersion` comparison against the bundled version with an actionable "update harness" message — not expressible in pure JSON Schema |
| In-code `password` scan | FR-004 forbids the key at *any* nesting depth; JSON Schema cannot cleanly express "no property named X anywhere", and a recursive scan yields a precise violation path |
| Separate CLI surface | FR-010 requires validation reachable outside a running job for connector/evaluator authoring |
