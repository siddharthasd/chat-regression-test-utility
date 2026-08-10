"""Job ORM model — the central entity (009 FR-001).

All 15 snapshot fields are immutable past ``draft``; ``created_by`` /
``created_at`` are immutable from creation. Immutability is enforced by the
repository layer (no ORM event listeners — research R7/R10), not here.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from harness.persistence.base import Base

if TYPE_CHECKING:
    from harness.persistence.models.utterance import Utterance

#: Job snapshot fields frozen once the Job leaves draft status (FR-005).
SNAPSHOT_FIELDS: frozenset[str] = frozenset(
    {
        "connector_id",
        "connector_name",
        "connector_endpoint_url",
        "connector_auth_descriptor",
        "connector_timeout_seconds",
        "connector_expects_per_row_password",
        "evaluation_agent_id",
        "evaluation_agent_name",
        "evaluator_endpoint_url",
        "evaluator_auth_descriptor",
        "evaluator_timeout_seconds",
        "evaluator_declared_scoring_dimensions",
        "evaluator_score_scale_min",
        "evaluator_score_scale_max",
        "total_utterance_count",
        "harness_version",
        "source_csv_filename",
    }
)


class Job(Base):
    """One regression run, with its snapshotted config and lifecycle state."""

    __tablename__ = "job"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    harness_version: Mapped[str] = mapped_column(String, nullable=False)
    source_csv_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    error_details: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Connector snapshot (immutable past draft) ---
    connector_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connector_name: Mapped[str | None] = mapped_column(String, nullable=True)
    connector_endpoint_url: Mapped[str | None] = mapped_column(String, nullable=True)
    connector_auth_descriptor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    connector_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connector_expects_per_row_password: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )

    # --- Evaluator snapshot (immutable past draft) ---
    evaluation_agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evaluation_agent_name: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluator_endpoint_url: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluator_auth_descriptor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluator_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluator_declared_scoring_dimensions: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    evaluator_score_scale_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluator_score_scale_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluator_scoring_thresholds: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- Headless submission metadata (020) ---
    submission_source: Mapped[str] = mapped_column(String(20), nullable=False, default="wizard")
    source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feature_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Aggregate counters ---
    total_utterance_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    utterances: Mapped[list[Utterance]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
