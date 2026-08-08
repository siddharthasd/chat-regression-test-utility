"""Add score_scale_min/max to evaluation_agent_registration and job.

Stores the declared numeric score scale (min and max bounds) alongside the
evaluator registration and the job-time evaluator snapshot. Both columns are
nullable so existing rows are unaffected (legacy path: null scale = no
range validation, raw analytics mean).

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    reg_cols = {c["name"] for c in inspector.get_columns("evaluation_agent_registration")}
    if "score_scale_min" not in reg_cols:
        op.add_column(
            "evaluation_agent_registration",
            sa.Column("score_scale_min", sa.Float, nullable=True),
        )
    if "score_scale_max" not in reg_cols:
        op.add_column(
            "evaluation_agent_registration",
            sa.Column("score_scale_max", sa.Float, nullable=True),
        )

    job_cols = {c["name"] for c in inspector.get_columns("job")}
    if "evaluator_score_scale_min" not in job_cols:
        op.add_column(
            "job",
            sa.Column("evaluator_score_scale_min", sa.Float, nullable=True),
        )
    if "evaluator_score_scale_max" not in job_cols:
        op.add_column(
            "job",
            sa.Column("evaluator_score_scale_max", sa.Float, nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    reg_cols = {c["name"] for c in inspector.get_columns("evaluation_agent_registration")}
    if "score_scale_max" in reg_cols:
        op.drop_column("evaluation_agent_registration", "score_scale_max")
    if "score_scale_min" in reg_cols:
        op.drop_column("evaluation_agent_registration", "score_scale_min")

    job_cols = {c["name"] for c in inspector.get_columns("job")}
    if "evaluator_score_scale_max" in job_cols:
        op.drop_column("job", "evaluator_score_scale_max")
    if "evaluator_score_scale_min" in job_cols:
        op.drop_column("job", "evaluator_score_scale_min")
