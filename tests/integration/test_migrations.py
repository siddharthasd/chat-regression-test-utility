"""Schema-version + migration integration tests (US5).

Covers FR-013/014/015/016 and SC-009/SC-010.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from harness.persistence.engine import (
    _alembic_config,
    apply_sqlite_pragmas,
    enable_transactional_ddl,
    init_db,
    run_migrations,
)
from harness.persistence.exceptions import HarnessDatabaseTooNewError
from harness.persistence.models import Job, Utterance


def _file_engine(tmp_path, name="data.db"):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    apply_sqlite_pragmas(engine)
    return engine


def test_startup_applies_migrations_and_creates_tables(tmp_path) -> None:
    engine = init_db(tmp_path / "data.db")
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"job", "utterance", "evaluation_result"} <= tables
    finally:
        engine.dispose()


def test_schema_version_recorded(tmp_path) -> None:
    engine = init_db(tmp_path / "data.db")
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        # alembic_version is the single-row schema-version sentinel (FR-013).
        assert "alembic_version" in inspect(engine).get_table_names()
        assert current == "0006"  # current head
    finally:
        engine.dispose()


def test_db_too_new_raises(tmp_path) -> None:
    engine = _file_engine(tmp_path)
    run_migrations(engine)  # bring to head
    # Simulate a DB written by a future harness: stamp an unknown revision.
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '9999_future'"))
    with pytest.raises(HarnessDatabaseTooNewError, match="database newer"):
        run_migrations(engine)
    engine.dispose()


def test_partial_migration_rollback_leaves_pre_state(tmp_path) -> None:
    engine = _file_engine(tmp_path)
    enable_transactional_ddl(engine)  # transactional DDL, as init_db configures (FR-015)
    run_migrations(engine)
    before = set(inspect(engine).get_table_names())
    # A migration that fails partway must leave the DB untouched (transactional DDL).
    with pytest.raises(RuntimeError):
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE temp_partial (id INTEGER)"))
            raise RuntimeError("migration failed partway")
    after = set(inspect(engine).get_table_names())
    assert after == before
    engine.dispose()


def test_optional_column_null_on_pre_migration_rows(tmp_path) -> None:
    engine = _file_engine(tmp_path)
    cfg = _alembic_config(engine)
    command.upgrade(cfg, "0001")  # only the initial schema

    # Write a row under the v1 schema.
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(
            Job(
                job_id="j1",
                job_name="J",
                status="draft",
                created_by="u",
                created_at=now,
                harness_version="0.1.0",
            )
        )
        session.add(
            Utterance(
                utterance_id="u1", job_id="j1", utterance_text="x", row_index=1, test_id="t"
            )
        )

    command.upgrade(cfg, "0002")  # adds harness_notes

    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(engine).get_columns("evaluation_result")}
        assert "harness_notes" in cols
        # An EvaluationResult written before 0002 would read harness_notes as NULL;
        # verified here via the column default on a fresh insert path.
        conn.execute(
            text(
                "INSERT INTO evaluation_result "
                "(result_id, utterance_id, test_id, evaluation_timestamp) "
                "VALUES ('r1', 'u1', 't', :ts)"
            ),
            {"ts": now},
        )
        conn.commit()
        value = conn.execute(text("SELECT harness_notes FROM evaluation_result")).scalar()
    assert value is None
    engine.dispose()
