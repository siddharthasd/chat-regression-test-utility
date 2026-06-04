# Phase 1 Data Model: Standard Evaluation Contract (Module 6)

**Date**: 2026-06-03
**Plan**: `specs/006-evaluation-contract/plan.md`

This module has **no database entities** — its "data model" is the wire-format schema plus the in-memory validation result types. The contract instance is persisted elsewhere (`EvaluationResult.normalizedContract`, `009 FR-003`).

---

## Entity 1: Standard Evaluation Contract (the schema)

A single versioned JSON Schema (Draft 2020-12) artifact. `BUNDLED_CONTRACT_VERSION = 1`.

### Required top-level fields (FR-002)

| Field | JSON type | Notes |
|---|---|---|
| `contractVersion` | string | Integer-as-string, `^[0-9]+$`. Numeric-compared to bundled (FR-015/016). |
| `utteranceId` | string | Globally unique (UUID v4 or equiv); harness-generated. |
| `utteranceText` | string | Original CSV `utteranceText` value. |
| `testId` | string | CSV-supplied row identity. |
| `conversationContext` | object \| null | v1 MUST be `null` (multi-turn reserved). Non-null permitted forward-compat. |
| `chatbotResponse` | object | See Entity 2. |
| `connectorId` | string | Producing connector's `ConnectorRegistration.connectorId` (`009 FR-001a`). |
| `timestamp` | string | ISO-8601 / RFC 3339 `date-time` (FR-013). |

### Extensibility (FR-005)

`additionalProperties` is left open (default `true`) at every object level. Unknown fields — top-level or nested — are conforming, never violations.

### Forbidden (FR-004)

A key named exactly `password` at **any** depth is a violation (`forbidden_field`), enforced by a recursive code scan, not the schema.

---

## Entity 2: `chatbotResponse` (nested object, FR-003)

| Sub-field | JSON type | Notes |
|---|---|---|
| `rawPayload` | any (object/array/string) | Schema-unconstrained (`true`). Raw chatbot response. |
| `normalizedText` | string | Plain-text rendering. Empty string `""` allowed. |
| `agentChain` | array of strings | Ordered agent ids. Empty `[]` valid; field MUST be present. |
| `metadata` | object | Free-form connector-specific. Empty `{}` valid; field MUST be present. |

---

## Entity 3: ValidationResult (in-memory, returned by `validate_contract`)

| Field | Type | Notes |
|---|---|---|
| `valid` | `bool` | True iff zero violations. |
| `violations` | `list[Violation]` | Empty when valid. Deterministic order (FR-011). |
| `contract_version` | `str \| None` | The instance's declared `contractVersion` (None if absent/non-string). |

---

## Entity 4: Violation (in-memory)

| Field | Type | Notes |
|---|---|---|
| `field_path` | `str` | Dotted/indexed path, e.g. `chatbotResponse.normalizedText`, `agentChain[2]`. |
| `kind` | `ViolationKind` (StrEnum) | `missing` / `wrong_type` / `bad_format` / `version_out_of_range` / `forbidden_field` / `schema` |
| `expected` | `str \| None` | Expected type/format/version where applicable. |
| `observed` | `str \| None` | Observed type/value where applicable. |
| `message` | `str` | Human-readable detail (FR-009). |

The harness maps a non-empty `violations` list to a per-row failure with `errorStage = "connector_normalization"` (FR-009) — that mapping lives in the orchestrator (`012`), not here.

---

## Version Comparison Semantics (FR-015 / FR-016)

```text
instance_v = int(instance["contractVersion"])    # FR-016 numeric, not lexicographic
bundled_v  = BUNDLED_CONTRACT_VERSION             # = 1

instance_v == bundled_v  → structurally validate against bundled schema
instance_v <  bundled_v  → accept (FR-006 additive-only-never-bumps ⇒ still conforms)
instance_v >  bundled_v  → version_out_of_range violation (names both; "update the harness")
```

## Versioning Policy (FR-006 / FR-007 — dev-time, not runtime)

- **Additive (no bump)**: add a new optional field.
- **Breaking (bump `contractVersion`)**: remove a field, rename a field, change a field's type, change a field's meaning, make an optional field required, or flip `additionalProperties` to forbidden.
