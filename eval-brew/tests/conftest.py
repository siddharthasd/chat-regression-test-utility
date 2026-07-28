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

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from harness.identity.context import IdentityContext
from harness.identity.resolution import TesterIdentity
from harness.persistence.engine import run_migrations


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


# --------------------------------------------------------------------------- #
# Persistence fixtures (009)                                                   #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session", autouse=True)
def _isolate_harness_paths(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point the harness key file at a temp dir for the whole test session.

    Keeps the real `~/.harness/` key untouched when app-factory / CLI tests
    call `bootstrap.initialize_harness()`. DATABASE_URL is left as-is so tests
    connect to the configured PostgreSQL instance.
    """
    base = tmp_path_factory.mktemp("harness_home")
    prev = {k: os.environ.get(k) for k in ("HARNESS_KEY_FILE", "HARNESS_SESSION_HTTPS_ONLY")}
    os.environ["HARNESS_KEY_FILE"] = str(base / "master.key")
    os.environ["HARNESS_SESSION_HTTPS_ONLY"] = "false"
    yield
    for key, value in prev.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Session-scoped PostgreSQL engine with all migrations applied once.

    Requires DATABASE_URL to be set. Skip the fixture (and dependent tests)
    when no database is configured.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — skipping database-backed tests")
    engine = create_engine(database_url, pool_pre_ping=True)
    run_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Function-scoped session with savepoint rollback for data isolation.

    Joins an outer transaction and restarts a SAVEPOINT after each inner
    commit, so repository code that commits still rolls back cleanly at
    teardown (research R11).
    """
    connection = db_engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans) -> None:  # noqa: ANN001, ARG001
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
