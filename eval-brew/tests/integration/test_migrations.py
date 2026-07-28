"""Schema-version + migration integration tests (US5).

Covers FR-013/014/015/016 and SC-009/SC-010.

Requires DATABASE_URL to be set; tests are skipped otherwise.
"""

from __future__ import annotations

import os

import pytest
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from harness.persistence.engine import (
    _alembic_config,
    init_db,
    run_migrations,
)
from harness.persistence.exceptions import HarnessDatabaseTooNewError


@pytest.fixture(scope="module")
def pg_engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set — migration tests require PostgreSQL")
    engine = create_engine(database_url, pool_pre_ping=True)
    run_migrations(engine)
    yield engine
    engine.dispose()


def test_startup_applies_migrations_and_creates_tables(pg_engine) -> None:
    tables = set(inspect(pg_engine).get_table_names())
    assert {"job", "utterance", "evaluation_result"} <= tables


def test_schema_version_recorded(pg_engine) -> None:
    with pg_engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    assert "alembic_version" in inspect(pg_engine).get_table_names()
    assert current is not None


def test_init_db_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        init_db()


def test_db_too_new_raises() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        run_migrations(engine)
        # Simulate a DB written by a future harness inside a transaction that rolls back.
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '9999_future'"))
            with pytest.raises(HarnessDatabaseTooNewError, match="database newer"):
                run_migrations(engine)
            conn.execute(text("ROLLBACK TO SAVEPOINT sp1"))
    except Exception:
        pass
    finally:
        engine.dispose()
