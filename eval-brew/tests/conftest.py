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
from sqlalchemy.pool import StaticPool

from harness.identity.context import IdentityContext
from harness.identity.resolution import TesterIdentity
from harness.persistence.engine import apply_sqlite_pragmas, run_migrations


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
    """Point the harness DB + key files at a temp dir for the whole test session.

    Keeps the real `~/.harness/` untouched when app-factory / CLI tests call
    `bootstrap.initialize_harness()` (which now runs `init_db()`), and gives the
    encryption utility an isolated key file.
    """
    base = tmp_path_factory.mktemp("harness_home")
    # DATABASE_URL must also be cleared: if it is set in the caller's environment it
    # takes precedence over HARNESS_DB_PATH inside init_db(), silently connecting every
    # test to the external DB and voiding all per-test SQLite isolation.
    prev = {k: os.environ.get(k) for k in ("HARNESS_DB_PATH", "HARNESS_KEY_FILE", "DATABASE_URL")}
    os.environ["HARNESS_DB_PATH"] = str(base / "data.db")
    os.environ["HARNESS_KEY_FILE"] = str(base / "master.key")
    os.environ.pop("DATABASE_URL", None)
    yield
    for key, value in prev.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Session-scoped in-memory SQLite engine with all migrations applied once.

    Uses StaticPool so the single in-memory connection (and thus the schema)
    persists across the session (research R11).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    apply_sqlite_pragmas(engine)
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
