"""Add utterance_intent column to evaluation_result (018-ext).

Stores the evaluator-identified intent for each utterance, enabling
intent-based score analytics grouping on the dashboard.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-08
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("evaluation_result")}
    if "utterance_intent" not in existing:
        op.add_column(
            "evaluation_result",
            sa.Column("utterance_intent", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("evaluation_result", "utterance_intent")
