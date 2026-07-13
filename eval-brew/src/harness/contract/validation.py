"""The contract validation utility (FR-008/009/010/011, research R3/R4).

``validate_contract`` runs, collecting ALL problems in deterministic order:
  1. Structural validation against the bundled Draft 2020-12 schema.
  2. A recursive scan for any ``password`` key at any depth (FR-004).
  3. The numeric ``contractVersion`` gate vs the bundled version (FR-015/016).
Never raises for arbitrary input.
"""

from __future__ import annotations

import re

from jsonschema.exceptions import ValidationError

from harness.contract.schema import BUNDLED_CONTRACT_VERSION, get_validator
from harness.contract.violations import ValidationResult, Violation, ViolationKind

_REQUIRED_RE = re.compile(r"'(?P<name>[^']+)' is a required property")
_KEYWORD_KIND = {
    "type": ViolationKind.WRONG_TYPE,
    "format": ViolationKind.BAD_FORMAT,
}


def validate_contract(instance: object) -> ValidationResult:
    """Validate ``instance`` against the Standard Evaluation Contract."""
    violations: list[Violation] = [_to_violation(err) for err in _sorted_errors(instance)]
    violations.extend(_scan_for_password(instance))

    cv_raw = instance.get("contractVersion") if isinstance(instance, dict) else None
    violations.extend(_version_gate(cv_raw))

    contract_version = cv_raw if isinstance(cv_raw, str) else None
    return ValidationResult(
        valid=not violations,
        violations=violations,
        contract_version=contract_version,
    )


# --------------------------------------------------------------------------- #
# Structural validation                                                       #
# --------------------------------------------------------------------------- #


def _sorted_errors(instance: object) -> list[ValidationError]:
    """All schema errors in a deterministic order (FR-011)."""
    return sorted(
        get_validator().iter_errors(instance),
        key=lambda e: (_format_path(e.absolute_path), str(e.validator)),
    )


def _format_path(path) -> str:  # noqa: ANN001 — jsonschema deque of str|int
    parts: list[str] = []
    for component in path:
        if isinstance(component, int):
            parts.append(f"[{component}]")
        else:
            parts.append(f".{component}" if parts else component)
    return "".join(parts)


def _to_violation(err: ValidationError) -> Violation:
    path = _format_path(err.absolute_path)
    if err.validator == "required":
        match = _REQUIRED_RE.search(err.message)
        name = match.group("name") if match else "?"
        return Violation(
            field_path=f"{path}.{name}" if path else name,
            kind=ViolationKind.MISSING,
            message=f"required field {name!r} is missing",
            expected=name,
        )
    kind = _KEYWORD_KIND.get(err.validator, ViolationKind.SCHEMA)
    expected = observed = None
    if kind is ViolationKind.WRONG_TYPE:
        expected = str(err.validator_value)
        observed = type(err.instance).__name__
    elif kind is ViolationKind.BAD_FORMAT:
        expected = str(err.validator_value)
        observed = repr(err.instance)
    return Violation(
        field_path=path or "<root>",
        kind=kind,
        message=err.message,
        expected=expected,
        observed=observed,
    )


# --------------------------------------------------------------------------- #
# password-forbidden-anywhere (FR-004)                                        #
# --------------------------------------------------------------------------- #


def _scan_for_password(node: object, path: str = "") -> list[Violation]:
    out: list[Violation] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if key == "password":
                out.append(
                    Violation(
                        field_path=child,
                        kind=ViolationKind.FORBIDDEN_FIELD,
                        message="contract MUST NOT contain a 'password' field (FR-004)",
                    )
                )
            out.extend(_scan_for_password(value, child))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            out.extend(_scan_for_password(item, f"{path}[{index}]"))
    return out


# --------------------------------------------------------------------------- #
# contractVersion numeric gate (FR-015 / FR-016)                              #
# --------------------------------------------------------------------------- #


def _version_gate(cv_raw: object) -> list[Violation]:
    # Shape problems (non-string, non-numeric) are already reported by the
    # schema's `type`/`pattern` keywords; only the numeric range is checked here.
    if not isinstance(cv_raw, str) or not cv_raw.isdigit():
        return []
    instance_version = int(cv_raw)  # numeric, not lexicographic (FR-016)
    if instance_version > BUNDLED_CONTRACT_VERSION:
        return [
            Violation(
                field_path="contractVersion",
                kind=ViolationKind.VERSION_OUT_OF_RANGE,
                message=(
                    f"contractVersion {instance_version} is newer than the bundled "
                    f"schema version {BUNDLED_CONTRACT_VERSION}; update the harness"
                ),
                expected=f"<= {BUNDLED_CONTRACT_VERSION}",
                observed=cv_raw,
            )
        ]
    return []
