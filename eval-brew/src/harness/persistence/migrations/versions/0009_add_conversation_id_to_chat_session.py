"""Add active_conversation_id to chat_session.

Stores the connector-supplied conversationId across turns so the harness
can forward it on subsequent requests, enabling multi-turn conversation
continuity in chat sessions. NULL means no conversationId has been
established yet for the session.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("chat_session")}

    if "active_conversation_id" not in existing:
        op.add_column(
            "chat_session",
            sa.Column("active_conversation_id", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = {c["name"] for c in inspector.get_columns("chat_session")}

    if "active_conversation_id" in existing:
        op.drop_column("chat_session", "active_conversation_id")
