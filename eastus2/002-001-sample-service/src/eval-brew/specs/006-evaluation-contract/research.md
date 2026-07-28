# Phase 0 Research: Standard Evaluation Contract (Module 6)

**Date**: 2026-06-03
**Plan**: `specs/006-evaluation-contract/plan.md`
**Spec**: `specs/006-evaluation-contract/spec.md`

Resolves the plan-level decisions the spec deferred to `/speckit-plan` (schema format, validation surface, version-gate mechanics). Each decision is directly codeable.

---

## R1: Schema Definition Format

**Decision**: **JSON Schema Draft 2020-12**, shipped as a single `.json` artifact under `src/harness/contract/schemas/standard_evaluation_contract.schema.json`. The schema names every required and optional field, types them, embeds per-field `description` annotations (FR-014), and leaves `additionalProperties` open at every level (FR-005).

**Rationale**: JSON Schema is the lingua franca for "validate any JSON object and report per-field violations"; it directly satisfies FR-001 (versioned artifact), FR-005 (additionalProperties), and FR-013 (format: date-time). Draft 2020-12 is the current standard and is fully supported by the `jsonschema` library.

**Alternatives considered**:
- **Pydantic models**: Couples the contract to Python classes and makes "publish the schema as a language-neutral artifact for connector/evaluator authors" awkward (the artifact becomes generated, not authored). Rejected.
- **OpenAPI 3.x fragment**: Heavier; the contract is a single object, not an API surface. Rejected.

---

## R2: Validation Library

**Decision**: `jsonschema>=4.21`, using `Draft202012Validator` with a `FormatChecker` so `format: "date-time"` is *asserted* (not merely annotated). Collect the full violation set via `validator.iter_errors(instance)` (not `validate()`, which raises on the first error) so FR-009's "list of per-field violations" is satisfied in one pass.

**Rationale**: `iter_errors` yields a `ValidationError` per problem, each carrying `.json_path`, `.validator` (the failing keyword → violation kind), `.validator_value` (expected), and `.instance` (observed) — exactly the detail FR-009/FR-010 require. 4.21 is the first release with the stable Draft 2020-12 format-assertion behavior used here.

**Alternatives considered**:
- `validate()` one-shot: raises on first error → can't return the full list. Rejected.
- `fastjsonschema` (compiled): faster but raises on first error and has weaker error introspection. The per-row volume (1k rows) doesn't justify it. Rejected.

---

## R3: `contractVersion` Numeric Gate (FR-015 / FR-016)

**Decision**: Enforce the version range in **code**, not in the schema. After structural validation, parse the instance's `contractVersion` string as an integer and compare to `BUNDLED_CONTRACT_VERSION`:
- `== bundled` → validate against bundled schema (already done structurally).
- `< bundled` → accepted (FR-006 additive-only-never-bumps guarantees structural conformance).
- `> bundled` → a `version_out_of_range` violation naming both the instance version and the bundled version, with remediation text "update the harness".

**Rationale**: FR-016 demands numeric (not lexicographic) comparison and FR-015 demands an actionable two-version message — neither is expressible in pure JSON Schema. The schema only constrains `contractVersion` to the shape `^[0-9]+$`; the numeric range check is code.

**Alternatives considered**:
- `enum`/`const` of accepted versions in the schema: can't express "≤ N" cleanly and produces a poor message. Rejected.

---

## R4: `password`-Forbidden-Anywhere (FR-004)

**Decision**: A deterministic recursive scan (`_scan_for_password`) walks the instance dict/list tree; any key named exactly `password` (case-sensitive) at any depth produces a `forbidden_field` violation whose path is the dotted/indexed location.

**Rationale**: JSON Schema cannot cleanly express "no property named X at arbitrary nesting depth" (`propertyNames`/`not` only apply per-object and don't recurse into unconstrained `additionalProperties` subtrees like `rawPayload`). A recursive scan is deterministic (FR-011) and yields a precise path (FR-009).

**Alternatives considered**:
- Per-object `propertyNames: { not: { const: "password" } }`: would have to be repeated on every object and still wouldn't cover the schema-unconstrained `rawPayload` subtree. Rejected.

---

## R5: Timestamp ISO-8601 Validation (FR-013)

**Decision**: `timestamp` is `type: string, format: "date-time"`; the validator is constructed with `format_checker=Draft202012Validator.FORMAT_CHECKER` so `date-time` is enforced as RFC 3339. Unix-epoch integers fail on `type` (not a string); malformed strings fail on `format`.

**Rationale**: Format assertion is opt-in in JSON Schema; enabling the format checker turns the annotation into a hard check, satisfying FR-013. `jsonschema`'s `date-time` checker requires no extra dependency for the RFC 3339 subset commonly emitted (it uses `fromisoformat`-style validation; the optional `rfc3339-validator` dep tightens it further but is not required for v1).

---

## R6: Extensibility / additionalProperties (FR-005)

**Decision**: Leave `additionalProperties` at its default (`true`) on every object in the schema; do **not** set it to `false` anywhere. `chatbotResponse.rawPayload` is typed as `true` (any JSON value) so connectors emit whatever the chatbot returns (Assumption: "owns the path TO it, not the shape AT it"). `chatbotResponse.metadata` is `type: object` with open properties.

**Rationale**: FR-005 mandates unknown fields validate as conforming; the default-open behavior is exactly that. Flipping `additionalProperties` to `false` would itself be a breaking change per FR-007.

---

## R7: Validation Surface (FR-010)

**Decision**: Two surfaces over one implementation:
1. `harness.contract.validate_contract(obj: dict) -> ValidationResult` — the canonical Python function used at runtime (by `012`) and in tests.
2. `harness contract validate <path.json>` — a thin Click command (in `cli/contract.py`) that reads a JSON file, calls `validate_contract`, prints the result (human + `--json`), and exits non-zero on non-conformance — for connector/evaluator authors developing outside a running job.

**Rationale**: FR-010 requires validation reachable for authoring use; a function covers runtime + tests, a CLI covers manual authoring. Both share the single `validate_contract` implementation, keeping behavior identical (FR-008/FR-011).

---

## R8: Bundled-Schema Loading & Version Source of Truth (FR-015)

**Decision**: The schema JSON is package data loaded once via `importlib.resources.files("harness.contract.schemas")`. `BUNDLED_CONTRACT_VERSION: int = 1` is a module constant in `contract/schema.py` and is the **single source of truth** for the runtime version gate; a `test_schema.py` test asserts it equals the integer parse of the schema's own declared version (a `const`/`description` marker in the schema) so the two never drift.

**Rationale**: FR-015 mandates exactly one bundled schema (the latest); no historical artifacts retained. Loading via `importlib.resources` works whether installed as a wheel or editable.

---

## R9: Breaking-Change Detection (US4 / SC-007)

**Decision**: Out of **runtime** scope. The versioning policy (FR-006/FR-007) is enforced as a **dev-time process check**: a documented review checklist plus a unit test (`test_breaking_change_policy`) that encodes the rule set (removed/renamed/retyped field or newly-required field ⇒ must bump `BUNDLED_CONTRACT_VERSION`). A full schema-diff tool is deferred; v1 ships the policy test as the "equivalent process check" the spec allows.

**Rationale**: SC-007 explicitly permits "CI check, codified review checklist, or equivalent". The runtime harness never needs to diff schemas; only contributors do.

---

## R10: Dependency Additions

**Decision**: Add to `pyproject.toml` `[project].dependencies`:
```
jsonschema>=4.21
```
No new dev dependencies. The bundled schema artifact ships as package data (ensure `tool.setuptools.package-data` or `include-package-data` picks up `*.json` under `harness/contract/schemas/`).

| Package | Min version | Reason |
|---|---|---|
| `jsonschema` | `>=4.21` | Draft 2020-12 validator + `iter_errors` + format-assertion |

---

*All deferred decisions resolved. A developer can implement `006` directly from these decisions.*
