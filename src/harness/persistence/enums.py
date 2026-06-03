"""Canonical enums and constant sets for the persistence layer.

The Job status enum is the parent spec's canonical seven-value lifecycle
(`009` spec Clarifications Q2). Values are stored lowercase as plain strings on
the ``Job.status`` column; this enum enforces valid values at the application
boundary (research R1 — avoids SQLite enum-migration pain).
"""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Canonical job lifecycle states (009 FR-001)."""

    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorStatus(StrEnum):
    """Per-row terminal error status on EvaluationResult (009 FR-003)."""

    FAILED = "failed"
    CANCELLED = "cancelled"


#: Statuses from which a Job may be deleted (009 FR-011).
DELETABLE_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.DRAFT, JobStatus.FAILED, JobStatus.CANCELLED}
)

#: Terminal statuses (009 spec / data-model state machine).
TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
)

#: The canonical 9-value error_stage enum (009 FR-003, per 012 FR-012).
ERROR_STAGES: frozenset[str] = frozenset(
    {
        "connector_transport",
        "connector_response",
        "connector_normalization",
        "connector_auth",
        "evaluator_transport",
        "evaluator_response",
        "evaluator_result",
        "evaluator_auth",
        "password_lookup",
    }
)
