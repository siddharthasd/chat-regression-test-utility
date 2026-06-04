"""Evaluator Registry & Management (Module 14): CRUD service + form/test-connection helpers.

Symmetric twin of `harness.connector_registry` over the evaluator side. The Flask
UI lives in `harness.ui.evaluator_registry`. Reuses 009 (repo writes/encryption),
008's reader/validator, harness.remote.auth, and 007's mock contract builder.
"""

from __future__ import annotations

from harness.evaluator_registry.forms import parse_evaluator_form
from harness.evaluator_registry.service import EvaluatorRegistryService, RegistrationInUseError
from harness.evaluator_registry.test_connection import TestConnectionResult, run_test_connection

__all__ = [
    "EvaluatorRegistryService",
    "RegistrationInUseError",
    "TestConnectionResult",
    "parse_evaluator_form",
    "run_test_connection",
]
