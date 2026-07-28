"""Add live chat tables and supports_sse columns (017 — Live Chat & Real-Time Evaluation).

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent ADD COLUMN: migration 0001 uses create_all() from current ORM models,
    # so the column may already exist when a fresh DB is migrated end-to-end.
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    conn_cols = {c["name"] for c in inspector.get_columns("connector_registration")}
    if "supports_sse" not in conn_cols:
        op.add_column(
            "connector_registration",
            sa.Column("supports_sse", sa.Boolean(), nullable=False, server_default="0"),
        )

    eval_cols = {c["name"] for c in inspector.get_columns("evaluation_agent_registration")}
    if "supports_sse" not in eval_cols:
        op.add_column(
            "evaluation_agent_registration",
            sa.Column("supports_sse", sa.Boolean(), nullable=False, server_default="0"),
        )

    existing_tables = set(inspector.get_table_names())
    if "chat_session" in existing_tables:
        return  # All chat tables already created by create_all (fresh DB migration 0001).

    op.create_table(
        "chat_session",
        sa.Column("chat_session_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("session_name", sa.String(255), nullable=False),
        sa.Column("owner_oid", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("test_id_enc", sa.Text(), nullable=False),
        sa.Column("test_password_enc", sa.Text(), nullable=False),
        sa.Column("connector_id", sa.String(36), nullable=True),
        sa.Column("connector_name", sa.String(255), nullable=True),
        sa.Column("connector_endpoint_url", sa.Text(), nullable=True),
        sa.Column("connector_auth_descriptor", sa.JSON(), nullable=True),
        sa.Column("connector_timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("evaluator_id", sa.String(36), nullable=True),
        sa.Column("evaluator_name", sa.String(255), nullable=True),
        sa.Column("evaluator_endpoint_url", sa.Text(), nullable=True),
        sa.Column("evaluator_auth_descriptor", sa.JSON(), nullable=True),
        sa.Column("evaluator_timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("evaluator_declared_scoring_dimensions", sa.JSON(), nullable=True),
    )
    op.create_index("ix_chat_session_owner_oid", "chat_session", ["owner_oid"])

    op.create_table(
        "chat_turn",
        sa.Column("turn_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("chat_session.chat_session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_chat_turn_session_id", "chat_turn", ["session_id"])

    op.create_table(
        "chat_turn_result",
        sa.Column("turn_result_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "turn_id",
            sa.String(36),
            sa.ForeignKey("chat_turn.turn_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("assembled_response", sa.Text(), nullable=True),
        sa.Column("normalized_contract", sa.JSON(), nullable=True),
        sa.Column("final_evaluation_result", sa.JSON(), nullable=True),
        sa.Column("error_stage", sa.String(50), nullable=True),
        sa.Column("error_details", sa.Text(), nullable=True),
    )
    op.create_index("ix_chat_turn_result_turn_id", "chat_turn_result", ["turn_id"])

    op.create_table(
        "evaluation_event",
        sa.Column("event_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "turn_id",
            sa.String(36),
            sa.ForeignKey("chat_turn.turn_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_evaluation_event_turn_id", "evaluation_event", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_event_turn_id", table_name="evaluation_event")
    op.drop_table("evaluation_event")
    op.drop_index("ix_chat_turn_result_turn_id", table_name="chat_turn_result")
    op.drop_table("chat_turn_result")
    op.drop_index("ix_chat_turn_session_id", table_name="chat_turn")
    op.drop_table("chat_turn")
    op.drop_index("ix_chat_session_owner_oid", table_name="chat_session")
    op.drop_table("chat_session")
    op.drop_column("evaluation_agent_registration", "supports_sse")
    op.drop_column("connector_registration", "supports_sse")
