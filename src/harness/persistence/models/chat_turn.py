"""ChatTurn ORM model — one user message within a live chat session (017)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.persistence.base import Base

if TYPE_CHECKING:
    from harness.persistence.models.chat_session import ChatSession
    from harness.persistence.models.chat_turn_result import ChatTurnResult
    from harness.persistence.models.evaluation_event import EvaluationEvent


class ChatTurn(Base):
    """One user/connector exchange within a ChatSession."""

    __tablename__ = "chat_turn"

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_session.chat_session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    # status: in_progress | completed | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped[ChatSession] = relationship(back_populates="turns")
    result: Mapped[ChatTurnResult | None] = relationship(
        uselist=False, cascade="all, delete-orphan", lazy="select"
    )
    evaluation_events: Mapped[list[EvaluationEvent]] = relationship(
        cascade="all, delete-orphan",
        order_by="EvaluationEvent.sequence_number",
        lazy="select",
    )
