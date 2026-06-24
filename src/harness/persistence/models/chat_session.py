"""ChatSession ORM model — one named live testing session (017 FR-LC-001).

All fields are immutable after creation except the ``turns`` relationship.
Credentials (test_id_enc, test_password_enc) are Fernet ciphertext at rest.
Connector and evaluator snapshots mirror the Job snapshotting convention.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.persistence.base import Base

if TYPE_CHECKING:
    from harness.persistence.models.chat_turn import ChatTurn


class ChatSession(Base):
    """One named live chat session owned by a tester."""

    __tablename__ = "chat_session"

    chat_session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_oid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Fernet-encrypted test credentials — never decrypted except in the pipeline
    test_id_enc: Mapped[str] = mapped_column(Text, nullable=False)
    test_password_enc: Mapped[str] = mapped_column(Text, nullable=False)

    # Connector snapshot (immutable; taken from ConnectorRegistration at creation)
    connector_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connector_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connector_endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    connector_auth_descriptor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    connector_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Evaluator snapshot (immutable; taken from EvaluationAgentRegistration at creation)
    evaluator_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evaluator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evaluator_endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluator_auth_descriptor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluator_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluator_declared_scoring_dimensions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    turns: Mapped[list[ChatTurn]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatTurn.created_at",
        lazy="select",
    )
