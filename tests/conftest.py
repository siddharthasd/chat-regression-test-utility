"""Shared pytest fixtures.

The `stub_identity` fixture lets tests replace the IdentityContext singleton's
value with a deterministic test identity (per
`specs/010-tester-identity/contracts/identity-context-api.md`'s test-fixture
surface). The fixture deliberately bypasses `_initialize_once()` and writes
directly to `IdentityContext._resolved` — this is the documented test-only
hatch. Production code MUST NOT use this pattern (CI/lint gates per SC-010).

The `stub_job_repository` fixture is a stand-in for 009's eventual
`JobRepository.create_draft()` surface. Used by US2's integration test
(test_job_creation_stamp.py) and will be available to downstream specs that
need a recordable Job-creation harness (e.g., 002's dashboard test, 003's
wizard test). Delete or replace when 009's real repository lands.
"""

from __future__ import annotations

import pytest

from harness.identity.context import IdentityContext
from harness.identity.resolution import TesterIdentity


class _StubIdentityContext:
    """Test helper that swaps the IdentityContext value for a single test."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    def with_identity(self, value: str) -> str:
        """Install `value` as the active tester identity for this test."""
        stub = TesterIdentity(value=value, resolution_source="stub")
        self._monkeypatch.setattr(IdentityContext, "_resolved", stub)
        return value


class StubJobRepository:
    """Stand-in for 009's eventual JobRepository.create_draft surface.

    Records every create_draft call so tests can assert what the wizard /
    consumer code passed in. Replaces the real SQLAlchemy session until
    009 lands.
    """

    def __init__(self) -> None:
        self.created_jobs: list[dict] = []

    def create_draft(
        self, name: str, description: str | None, createdBy: str
    ) -> dict:
        record = {
            "jobName": name,
            "description": description,
            "createdBy": createdBy,
            "status": "draft",
        }
        self.created_jobs.append(record)
        return record


@pytest.fixture
def stub_identity(monkeypatch: pytest.MonkeyPatch) -> _StubIdentityContext:
    """Yield a stub-identity helper. Reverts on test teardown via monkeypatch."""
    return _StubIdentityContext(monkeypatch)


@pytest.fixture
def stub_job_repository() -> StubJobRepository:
    """Yield a fresh stub Job repository (cleared per test)."""
    return StubJobRepository()
