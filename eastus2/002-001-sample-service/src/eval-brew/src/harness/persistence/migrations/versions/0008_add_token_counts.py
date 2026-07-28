"""Add token count columns to evaluation_result.

Adds connector_token_count, evaluator_token_count, and total_token_count.
All three are nullable integers; NULL means the connector/evaluator did not
report token usage (e.g. non-LLM connector), not zero tokens.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("evaluation_result")}

    if "connector_token_count" not in existing:
        op.add_column("evaluation_result", sa.Column("connector_token_count", sa.Integer, nullable=True))
    if "evaluator_token_count" not in existing:
        op.add_column("evaluation_result", sa.Column("evaluator_token_count", sa.Integer, nullable=True))
    if "total_token_count" not in existing:
        op.add_column("evaluation_result", sa.Column("total_token_count", sa.Integer, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("evaluation_result")}

    for col in ("total_token_count", "evaluator_token_count", "connector_token_count"):
        if col in existing:
            op.drop_column("evaluation_result", col)
