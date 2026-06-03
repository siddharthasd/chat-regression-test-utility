"""EvaluationAgentRegistration ORM model — a registered evaluator (009 FR-001b).

Same auth/encryption rules as ConnectorRegistration. Intentional asymmetries:
no ``expects_per_row_password``; ``description`` is required (not optional);
carries an ordered ``declared_scoring_dimensions`` list. Managed by module 014.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from harness.persistence.base import Base


class EvaluationAgentRegistration(Base):
    """A persisted record describing a remote evaluator service."""

    __tablename__ = "evaluation_agent_registration"

    evaluation_agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String, nullable=False)
    auth_descriptor: Mapped[dict] = mapped_column(JSON, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    declared_scoring_dimensions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
