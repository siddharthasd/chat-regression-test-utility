"""Result types returned by ``validate_contract`` (data-model.md, validation-api.md)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ViolationKind(StrEnum):
    """Category of a single contract violation."""

    MISSING = "missing"  # required field absent (FR-002/003)
    WRONG_TYPE = "wrong_type"  # type mismatch
    BAD_FORMAT = "bad_format"  # e.g. timestamp not ISO-8601 (FR-013)
    VERSION_OUT_OF_RANGE = "version_out_of_range"  # contractVersion > bundled (FR-015)
    FORBIDDEN_FIELD = "forbidden_field"  # a "password" key anywhere (FR-004)
    SCHEMA = "schema"  # any other schema-keyword failure


@dataclass(frozen=True)
class Violation:
    """One per-field conformance problem (FR-009)."""

    field_path: str
    kind: ViolationKind
    message: str
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a candidate contract instance."""

    valid: bool
    violations: list[Violation]
    contract_version: str | None
