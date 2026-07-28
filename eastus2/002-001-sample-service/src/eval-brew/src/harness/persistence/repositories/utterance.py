"""UtteranceRepository (009 FR-002/FR-006, contract repository-api.md).

Rows are immutable once the parent Job leaves ``draft`` (FR-006): both
``bulk_create`` and ``delete_by_job`` refuse when the parent is past draft.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harness.persistence.enums import JobStatus
from harness.persistence.exceptions import JobNotFoundError, UtteranceImmutableError
from harness.persistence.models import Job, Utterance
from harness.persistence.repositories.types import UtteranceCreateData


class UtteranceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def bulk_create(
        self, job_id: str, rows: list[UtteranceCreateData]
    ) -> list[Utterance]:
        self._require_draft_parent(job_id)
        utterances = [
            Utterance(
                utterance_id=str(uuid.uuid4()),
                job_id=job_id,
                utterance_text=row["utterance_text"],
                row_index=row["row_index"],
                test_id=row["test_id"],
                extra_metadata=row.get("extra_metadata"),
            )
            for row in rows
        ]
        self._session.add_all(utterances)
        self._session.flush()
        return utterances

    def get_by_job_ordered(self, job_id: str) -> list[Utterance]:
        return list(
            self._session.scalars(
                select(Utterance)
                .where(Utterance.job_id == job_id)
                .order_by(Utterance.row_index.asc())
            )
        )

    def delete_by_job(self, job_id: str) -> int:
        self._require_draft_parent(job_id)
        utterances = self.get_by_job_ordered(job_id)
        for utt in utterances:
            self._session.delete(utt)
        self._session.flush()
        return len(utterances)

    def count_by_job(self, job_id: str) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(Utterance)
                .where(Utterance.job_id == job_id)
            )
            or 0
        )

    def _require_draft_parent(self, job_id: str) -> None:
        job = self._session.get(Job, job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status != JobStatus.DRAFT:
            raise UtteranceImmutableError(job_id, "<utterance set>")
