"""Utterance ORM model — one persisted CSV data row (009 FR-002).

Has NO ``password`` / ``encryptedPassword`` column — per parent FR-010 the
per-row CSV password is in-memory only and never persisted (FR-009). The
absence is verified by a test introspecting ``Utterance.__table__.columns``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.persistence.base import Base

if TYPE_CHECKING:
    from harness.persistence.models.evaluation_result import EvaluationResult
    from harness.persistence.models.job import Job

#: Utterance fields frozen once the parent Job leaves draft status (FR-006).
IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {"utterance_text", "row_index", "test_id", "utterance_id", "job_id"}
)


class Utterance(Base):
    """One row from the source CSV (one per data row), minus password."""

    __tablename__ = "utterance"

    utterance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("job.job_id", ondelete="CASCADE"), nullable=False
    )
    utterance_text: Mapped[str] = mapped_column(String, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    test_id: Mapped[str] = mapped_column(String, nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    job: Mapped[Job] = relationship(back_populates="utterances")
    evaluation_result: Mapped[EvaluationResult | None] = relationship(
        back_populates="utterance", uselist=False, cascade="all, delete-orphan"
    )
