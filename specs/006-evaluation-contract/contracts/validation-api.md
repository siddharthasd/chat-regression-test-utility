# Contract: Validation API

**Module**: `harness.contract`
**Stability**: Internal-stable — consumed by `012` (orchestrator, per-row boundary), and by connector/evaluator authors via re-export.

---

## Public API

```python
BUNDLED_CONTRACT_VERSION: int   # = 1 — the single bundled schema's version (FR-015)

def validate_contract(instance: object) -> ValidationResult:
    """Validate any JSON-decoded object against the Standard Evaluation Contract.

    Performs, in order, collecting ALL problems (never raises on bad input):
      1. Structural validation against the bundled Draft 2020-12 schema
         (required fields, types, date-time format) — FR-002/003/013.
      2. Recursive scan for any key named "password" at any depth — FR-004.
      3. Numeric contractVersion gate vs BUNDLED_CONTRACT_VERSION — FR-015/016.

    Deterministic: identical input → identical result (FR-011). Never raises for
    malformed input — a non-dict or empty object yields valid=False with
    `missing` violations for the absent required fields (spec edge case).
    """
```

### `ValidationResult` (dataclass, frozen)

```python
@dataclass(frozen=True)
class ValidationResult:
    valid: bool                      # True iff violations == []
    violations: list[Violation]      # deterministic order
    contract_version: str | None     # instance's declared contractVersion, if a string
```

### `Violation` (dataclass, frozen)

```python
@dataclass(frozen=True)
class Violation:
    field_path: str                  # e.g. "chatbotResponse.normalizedText", "agentChain[2]", "" (root)
    kind: ViolationKind
    message: str                     # human-readable (FR-009)
    expected: str | None = None
    observed: str | None = None
```

### `ViolationKind` (StrEnum)

```python
class ViolationKind(StrEnum):
    MISSING = "missing"                       # required field absent
    WRONG_TYPE = "wrong_type"                 # type mismatch
    BAD_FORMAT = "bad_format"                 # e.g. timestamp not ISO-8601 (FR-013)
    VERSION_OUT_OF_RANGE = "version_out_of_range"  # contractVersion > bundled (FR-015)
    FORBIDDEN_FIELD = "forbidden_field"       # a "password" key anywhere (FR-004)
    SCHEMA = "schema"                         # any other schema-keyword failure
```

---

## Behavioural Contract

1. `validate_contract(x).valid is True` **iff** `violations == []`.
2. For a missing required field, exactly one `MISSING` violation whose `field_path` names that field (SC-002).
3. For a type mismatch, one `WRONG_TYPE` violation naming `expected` and `observed` types (SC-003).
4. For `contractVersion` numerically greater than `BUNDLED_CONTRACT_VERSION`, one `VERSION_OUT_OF_RANGE` violation whose `message` names both the instance version and the bundled version and suggests updating the harness (SC-004).
5. Unknown extension fields never produce a violation (SC-005, FR-005).
6. A `password` key at any depth produces a `FORBIDDEN_FIELD` violation with its path (FR-004).
7. Calling twice on the same input yields equal `ValidationResult`s — same flag, same violation list order/content (SC-009, FR-011).
8. The function never raises for arbitrary JSON input; a non-conforming or non-object input returns `valid=False` (spec edge case: "must not crash").
