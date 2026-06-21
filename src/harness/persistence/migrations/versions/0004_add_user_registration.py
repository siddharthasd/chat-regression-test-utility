"""Add user_registration table (015 — Azure AD user registry).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_registration",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("azure_oid", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_registration_email", "user_registration", ["email"], unique=True)
    op.create_index("ix_user_registration_azure_oid", "user_registration", ["azure_oid"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_registration_azure_oid", table_name="user_registration")
    op.drop_index("ix_user_registration_email", table_name="user_registration")
    op.drop_table("user_registration")
