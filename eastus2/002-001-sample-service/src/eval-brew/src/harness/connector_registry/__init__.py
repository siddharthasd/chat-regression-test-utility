"""Connector Registry & Management (Module 13): CRUD service + form/test-connection helpers.

The Flask UI lives in `harness.ui.connector_registry`; this package holds the
framework-agnostic service layer. Reuses 009 (repo writes/encryption), 007's
reader (read API), and harness.remote.auth + 006 (test-connection).
"""

from __future__ import annotations

from harness.connector_registry.forms import parse_connector_form
from harness.connector_registry.service import ConnectorRegistryService, RegistrationInUseError
from harness.connector_registry.test_connection import TestConnectionResult, run_test_connection

__all__ = [
    "ConnectorRegistryService",
    "RegistrationInUseError",
    "TestConnectionResult",
    "parse_connector_form",
    "run_test_connection",
]
