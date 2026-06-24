"""ChatTurnResult ORM model — assembled output for one completed or failed turn (017)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from harness.persistence.base import Base


class ChatTurnResult(Base):
    """One-to-one result record for a ChatTurn; written in a single batch at turn end."""

    __tablename__ = "chat_turn_result"

    turn_result_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_turn.turn_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    assembled_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_contract: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_evaluation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # error_stage: connector_stream | connector_normalization | evaluator_stream | server_restart
    error_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
