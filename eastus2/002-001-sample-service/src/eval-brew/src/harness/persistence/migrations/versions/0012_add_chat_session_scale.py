"""Add evaluator scale snapshot columns to chat_session.

chat_session was created before BL-005 added score scale to evaluator registrations.
Adding evaluator_score_scale_min and evaluator_score_scale_max so that the chat session
detail analytics can normalise scores using the same scale as batch job analytics.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    cols = {c["name"] for c in inspector.get_columns("chat_session")}
    if "evaluator_score_scale_min" not in cols:
        op.add_column(
            "chat_session",
            sa.Column("evaluator_score_scale_min", sa.Float, nullable=True),
        )
    if "evaluator_score_scale_max" not in cols:
        op.add_column(
            "chat_session",
            sa.Column("evaluator_score_scale_max", sa.Float, nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    cols = {c["name"] for c in inspector.get_columns("chat_session")}
    if "evaluator_score_scale_min" in cols:
        op.drop_column("chat_session", "evaluator_score_scale_min")
    if "evaluator_score_scale_max" in cols:
        op.drop_column("chat_session", "evaluator_score_scale_max")
