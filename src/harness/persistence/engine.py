"""Engine creation, SQLite PRAGMA tuning, session factory, and startup migration.

``init_db()`` is the bootstrap entry point: it resolves the DB path, ensures the
parent directory, builds a PRAGMA-tuned engine, runs pending Alembic migrations
(or refuses to start if the DB is newer than the harness), and binds the shared
``SessionLocal`` factory. See research R2/R3/R6.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from harness.persistence.exceptions import HarnessDatabaseTooNewError

#: Shared session factory. Bound to a concrete engine by ``init_db()``.
SessionLocal = sessionmaker(expire_on_commit=False)

_engine: Engine | None = None
DEFAULT_DB_FILENAME = "data.db"


def resolve_db_path() -> Path:
    """Resolve the DB file path: ``HARNESS_DB_PATH`` env var, else default (FR-017)."""
    override = os.environ.get("HARNESS_DB_PATH")
    if override:
        return Path(override)
    return Path.home() / ".harness" / DEFAULT_DB_FILENAME


def _ensure_directory(db_path: Path) -> None:
    """Create the DB file's parent directory if it does not exist (FR-018)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def apply_sqlite_pragmas(engine: Engine) -> None:
    """Attach a connect-time listener applying the four SQLite PRAGMAs (R2)."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def enable_transactional_ddl(engine: Engine) -> None:
    """Make SQLite DDL participate in transactions so failed migrations roll back.

    pysqlite auto-commits before DDL by default, which would let a migration that
    fails partway leave partial schema behind (violating FR-015). The documented
    SQLAlchemy recipe — disable the driver's implicit BEGIN and emit BEGIN
    ourselves — gives true transactional DDL on SQLite (research R3).
    """

    @event.listens_for(engine, "connect")
    def _disable_autobegin(dbapi_conn, _connection_record):  # noqa: ANN001
        dbapi_conn.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_begin(conn):  # noqa: ANN001
        conn.exec_driver_sql("BEGIN")


def _alembic_config(engine: Engine):
    """Build an Alembic Config bound to an existing engine/connection."""
    from alembic.config import Config

    migrations_dir = Path(__file__).parent / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    cfg.attributes["connection"] = engine
    return cfg


def run_migrations(engine: Engine) -> None:
    """Apply pending migrations, or raise if the DB is newer than the harness.

    - DB at head → no-op.
    - DB at an unknown (future) revision → ``HarnessDatabaseTooNewError`` (FR-016).
    - DB older / fresh → ``upgrade(head)`` (FR-014).
    """
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = _alembic_config(engine)
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()

    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()

    if current == head:
        return

    if current is not None:
        known = {rev.revision for rev in script.walk_revisions()}
        if current not in known:
            # DB written by a newer harness that knows a revision we don't.
            raise HarnessDatabaseTooNewError()

    command.upgrade(cfg, "head")


def init_db(db_path: Path | str | None = None) -> Engine:
    """Startup bootstrap: prepare the DB and bind ``SessionLocal``.

    Returns the bound engine. Raises ``HarnessDatabaseTooNewError`` if the
    on-disk schema is newer than this harness (FR-016).
    """
    global _engine
    path = Path(db_path) if db_path is not None else resolve_db_path()
    _ensure_directory(path)
    # check_same_thread=False lets the orchestrator's per-job worker threads (012)
    # open sessions off any thread; NullPool gives each session its OWN connection
    # so two overlapping workers never share a single SQLite connection (which is
    # unsafe even with check_same_thread=False). WAL + busy_timeout serialize the
    # short per-row writes safely in the single-process harness (012 research R2).
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    apply_sqlite_pragmas(engine)
    enable_transactional_ddl(engine)
    run_migrations(engine)
    SessionLocal.configure(bind=engine)
    _engine = engine
    return engine


def get_engine() -> Engine:
    """Return the engine bound by ``init_db()``; raise if not yet initialized."""
    if _engine is None:
        raise RuntimeError("init_db() has not been called")
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session wrapped in a transaction (commit on success, rollback on error).

    The canonical entry point for cross-entity atomic writes (FR-020, research R6)::

        with get_session() as session:
            JobRepository(session).increment_processed_count(job_id)
            EvaluationResultRepository(session).create(...)
        # both writes commit together, or neither does
    """
    session = SessionLocal()
    try:
        with session.begin():
            yield session
    finally:
        session.close()
