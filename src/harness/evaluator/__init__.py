"""Evaluation Agent Framework (Module 7): evaluator wire-protocol HTTP client.

Consumer-side twin of `harness.connector`. Per-row dispatch POSTs a Standard
Evaluation Contract instance and validates the returned EvaluationResult::

    from harness.evaluator import dispatch_evaluation, EvaluatorSnapshot
    result = dispatch_evaluation(snapshot, contract)

Reuses 009 (evaluator registry + encryption). The EvaluationResult shape is
validated here (not via 006's validate_contract).
"""

from __future__ import annotations

from harness.evaluator.auth import build_auth_headers
from harness.evaluator.client import dispatch_evaluation
from harness.evaluator.registry import EvaluatorListEntry, EvaluatorRegistryReader
from harness.evaluator.result import VERDICTS, EvaluatorResult, EvaluatorSnapshot
from harness.evaluator.validation import compute_harness_annotations, validate_evaluation_result

__all__ = [
    "VERDICTS",
    "EvaluatorListEntry",
    "EvaluatorRegistryReader",
    "EvaluatorResult",
    "EvaluatorSnapshot",
    "build_auth_headers",
    "compute_harness_annotations",
    "dispatch_evaluation",
    "validate_evaluation_result",
]
