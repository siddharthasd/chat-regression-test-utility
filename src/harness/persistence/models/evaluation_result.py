"""EvaluationResult ORM model — the per-row trace (009 FR-003).

At most one per Utterance (UNIQUE constraint on ``utterance_id``). The
agent-emitted ``metadata`` field maps to a SQL column named ``metadata`` but is
exposed as the Python attribute ``result_metadata`` to avoid clashing with
SQLAlchemy's reserved ``Base.metadata``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.persistence.base import Base

if TYPE_CHECKING:
    from harness.persistence.models.utterance import Utterance


class EvaluationResult(Base):
    """Per-row result of processing one Utterance (connector + evaluator trace)."""

    __tablename__ = "evaluation_result"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    utterance_id: Mapped[str] = mapped_column(
        ForeignKey("utterance.utterance_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    test_id: Mapped[str] = mapped_column(String, nullable=False)
    raw_chatbot_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_contract: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluation_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evaluation_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)
    evaluation_scores: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # SQL column is "metadata"; attribute renamed to dodge Base.metadata clash.
    result_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    harness_annotations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_details: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluation_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    utterance: Mapped[Utterance] = relationship(back_populates="evaluation_result")
