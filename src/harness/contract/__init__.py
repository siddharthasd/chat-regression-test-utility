"""Standard Evaluation Contract (Module 6): bundled schema + validation utility.

Public surface consumed at runtime by the orchestrator (012) and by
connector/evaluator authors::

    from harness.contract import validate_contract
    result = validate_contract(instance)
    if not result.valid:
        for v in result.violations:
            ...
"""

from __future__ import annotations

from harness.contract.schema import BUNDLED_CONTRACT_VERSION
from harness.contract.validation import validate_contract
from harness.contract.violations import ValidationResult, Violation, ViolationKind

__all__ = [
    "BUNDLED_CONTRACT_VERSION",
    "ValidationResult",
    "Violation",
    "ViolationKind",
    "validate_contract",
]
