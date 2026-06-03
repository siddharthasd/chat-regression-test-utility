"""Module 3 (010): Tester Identity & Test Credentials.

Public API surface per `specs/010-tester-identity/contracts/identity-context-api.md`.
"""

from harness.identity.context import IdentityContext
from harness.identity.resolution import (
    ResolutionSource,
    TesterIdentity,
    resolve_tester_identity,
)

__all__ = [
    "IdentityContext",
    "ResolutionSource",
    "TesterIdentity",
    "resolve_tester_identity",
]
