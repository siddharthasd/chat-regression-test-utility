"""EvaluationEvent ORM model — one streaming event from the evaluator (017)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from harness.persistence.base import Base


class EvaluationEvent(Base):
    """One structured SSE event emitted by the evaluator during a turn."""

    __tablename__ = "evaluation_event"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_turn.turn_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Known types: score_update | warning | insight | diagnostic | final
    # Unknown types: persisted as-is for forward compatibility
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
