"""Add an optional EvaluationResult column to exercise the migration path.

Demonstrates FR-016: a later schema version adds a nullable column that reads as
NULL for rows written under the prior schema. ``harness_notes`` is intentionally
NOT mapped on the ORM model — it exists only to prove forward-migration of an
existing data file.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_result",
        sa.Column("harness_notes", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_result", "harness_notes")
