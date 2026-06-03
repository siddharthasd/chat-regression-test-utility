"""Persistence layer: ORM models, repositories, encryption, and migrations.

All reads/writes go through the repository layer (no raw SQL outside migration
files; no ORM event listeners for business rules — research R7/R10). Cross-entity
writes that belong together MUST share one transaction (FR-020); use
``get_session()`` as the atomic unit of work::

    from harness.persistence import get_session
    from harness.persistence.repositories import JobRepository, EvaluationResultRepository

    with get_session() as session:
        EvaluationResultRepository(session).create(...)
        JobRepository(session).increment_processed_count(job_id)
    # both commit together, or neither does (crash-safe per FR-020)
"""

from __future__ import annotations

from harness.persistence.engine import SessionLocal, get_session, init_db

__all__ = ["SessionLocal", "get_session", "init_db"]
