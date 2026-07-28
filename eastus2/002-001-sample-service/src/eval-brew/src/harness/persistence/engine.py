"""Engine creation, session factory, and startup migration.

``init_db()`` is the bootstrap entry point: it builds a database engine, runs
pending Alembic migrations (or refuses to start if the DB is newer than the
harness), and binds the shared ``SessionLocal`` factory.

``DATABASE_URL`` must be set to a valid PostgreSQL SQLAlchemy URL. The harness
does not support any other backend.

When ``HARNESS_PG_USE_MANAGED_IDENTITY=true``, the engine uses an Azure AD
token (via ``DefaultAzureCredential``) as the PostgreSQL password instead of a
static credential. ``DATABASE_URL`` still supplies the host/port/dbname/user but
its password component is ignored. This is the required mode for AKS deployments
that authenticate to Azure PostgreSQL Flexible Server via workload identity.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from harness.persistence.exceptions import HarnessDatabaseTooNewError

log = structlog.get_logger(__name__)

_PG_AAD_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def _make_pg_token_creator(database_url: str):
    """Return a psycopg2 creator that injects a fresh Azure AD token as the password.

    ``DefaultAzureCredential`` covers AKS Workload Identity, node-level Managed
    Identity, and Azure CLI (for local testing). ``get_token()`` caches the token
    internally and only refreshes it when it nears expiry, so calling it on every
    new connection is safe and cheap.
    """
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(database_url)
    host = parsed.hostname or ""
    port = parsed.port or 5432
    dbname = (parsed.path or "").lstrip("/")
    user = parsed.username or ""
    sslmode = parse_qs(parsed.query).get("sslmode", ["require"])[0]

    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()

    def creator():
        import psycopg2

        token = credential.get_token(_PG_AAD_SCOPE)
        return psycopg2.connect(
            host=host, port=port, dbname=dbname, user=user,
            password=token.token, sslmode=sslmode,
        )

    return creator


#: Shared session factory. Bound to a concrete engine by ``init_db()``.
SessionLocal = sessionmaker(expire_on_commit=False)

_engine: Engine | None = None


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
        log.info("db.migrations.at_head", revision=head)
        return

    if current is not None:
        known = {rev.revision for rev in script.walk_revisions()}
        if current not in known:
            log.error("db.migrations.schema_too_new", current_revision=current, known_head=head)
            raise HarnessDatabaseTooNewError()

    # Count pending revisions: walk_revisions() goes head→base; stop at current.
    pending = 0
    for rev in script.walk_revisions():
        if rev.revision == current:
            break
        pending += 1
    log.info(
        "db.migrations.applying",
        from_revision=current or "none",
        to_revision=head,
        count=pending,
    )
    command.upgrade(cfg, "head")
    log.info("db.migrations.done", revision=head, applied=pending)


def init_db() -> Engine:
    """Startup bootstrap: prepare the DB and bind ``SessionLocal``.

    Returns the bound engine. Raises ``HarnessDatabaseTooNewError`` if the
    schema is newer than this harness (FR-016). Raises ``RuntimeError`` if
    ``DATABASE_URL`` is not set.
    """
    global _engine
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. A PostgreSQL connection string is required. "
            "Example: postgresql+psycopg2://user:pass@host:5432/dbname\n"
            "For AKS managed-identity deployments omit the password and set "
            "HARNESS_PG_USE_MANAGED_IDENTITY=true."
        )
    if _engine is not None:
        _engine.dispose()

    use_managed_identity = os.environ.get("HARNESS_PG_USE_MANAGED_IDENTITY", "").lower() in {
        "1", "true", "yes"
    }
    # pool_pre_ping reconnects silently after firewall/server-side idle timeouts.
    # pool_size=2 / max_overflow=3 caps each worker at 5 connections; with the
    # default workers=cpu*2+1 formula, a 2-vCPU host (5 workers) uses 25 connections
    # — well within Azure Flexible Server B1ms's max_connections=50.
    if use_managed_identity:
        # creator= bypasses the URL's credential fields; SQLAlchemy uses the URL
        # only for dialect detection. pool_pre_ping ensures a stale connection
        # (expired token) is detected and replaced with a fresh one on next checkout.
        engine = create_engine(
            database_url,
            creator=_make_pg_token_creator(database_url),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
        )
        log.info(
            "db.backend",
            backend="postgresql",
            auth="managed-identity",
            url=engine.url.render_as_string(hide_password=True),
        )
    else:
        engine = create_engine(database_url, pool_pre_ping=True, pool_size=2, max_overflow=3)
        log.info("db.backend", backend="postgresql", url=engine.url.render_as_string(hide_password=True))
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
