"""Add headless job metadata columns to the job table (020).

Adds submission_source (wizard/api), source_system, product_name,
and feature_name. Existing rows default to submission_source='wizard';
the three metadata columns are NULL.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("job")}

    if "submission_source" not in existing:
        op.add_column(
            "job",
            sa.Column(
                "submission_source",
                sa.String(20),
                nullable=False,
                server_default=sa.text("'wizard'"),
            ),
        )
    if "source_system" not in existing:
        op.add_column("job", sa.Column("source_system", sa.String(255), nullable=True))
    if "product_name" not in existing:
        op.add_column("job", sa.Column("product_name", sa.String(255), nullable=True))
    if "feature_name" not in existing:
        op.add_column("job", sa.Column("feature_name", sa.String(255), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("job")}

    for col in ("feature_name", "product_name", "source_system", "submission_source"):
        if col in existing:
            op.drop_column("job", col)
