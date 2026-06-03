"""Alembic migration environment.

``target_metadata`` is ``Base.metadata`` (with all models imported) for
``--autogenerate`` support. When ``init_db()`` runs migrations at startup it
injects the live engine via ``config.attributes['connection']`` (research R3).
SQLite ALTERs run in batch mode so later migrations can alter columns.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import all models so Base.metadata is fully populated.
import harness.persistence.models  # noqa: F401
from harness.persistence.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to a script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection (injected engine or own engine)."""
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
