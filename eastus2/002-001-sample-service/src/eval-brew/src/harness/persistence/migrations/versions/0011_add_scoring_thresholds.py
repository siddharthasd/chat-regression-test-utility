"""Add scoring_thresholds to evaluation_agent_registration and job.

Stores optional per-dimension pass/warn threshold declarations alongside the
evaluator registration and the job-time evaluator snapshot. Both columns are
nullable so existing rows are unaffected (legacy path: null thresholds =
no threshold display).

Threshold format:
    {"relevance": {"pass": 0.80, "warn": 0.60}, ...}

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    reg_cols = {c["name"] for c in inspector.get_columns("evaluation_agent_registration")}
    if "scoring_thresholds" not in reg_cols:
        op.add_column(
            "evaluation_agent_registration",
            sa.Column("scoring_thresholds", sa.JSON, nullable=True),
        )

    job_cols = {c["name"] for c in inspector.get_columns("job")}
    if "evaluator_scoring_thresholds" not in job_cols:
        op.add_column(
            "job",
            sa.Column("evaluator_scoring_thresholds", sa.JSON, nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    reg_cols = {c["name"] for c in inspector.get_columns("evaluation_agent_registration")}
    if "scoring_thresholds" in reg_cols:
        op.drop_column("evaluation_agent_registration", "scoring_thresholds")

    job_cols = {c["name"] for c in inspector.get_columns("job")}
    if "evaluator_scoring_thresholds" in job_cols:
        op.drop_column("job", "evaluator_scoring_thresholds")
