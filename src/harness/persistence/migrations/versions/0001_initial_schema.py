"""Initial schema: Job, Utterance, EvaluationResult, ConnectorRegistration,
EvaluationAgentRegistration (009 FR-013).

Creates all five entity tables from the ORM metadata. Alembic's own
``alembic_version`` table is the single-row schema-version sentinel (research
R3 — no separate hand-rolled version table).

Revision ID: 0001
Revises:
Create Date: 2026-06-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Import models to populate Base.metadata, then create every table.
    import harness.persistence.models  # noqa: F401
    from harness.persistence.base import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    import harness.persistence.models  # noqa: F401
    from harness.persistence.base import Base

    Base.metadata.drop_all(bind=op.get_bind())
