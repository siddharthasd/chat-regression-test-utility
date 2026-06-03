"""EvaluationResultRepository (009 FR-003/FR-003a, contract repository-api.md)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from harness.persistence.enums import ErrorStatus
from harness.persistence.models import EvaluationResult, Utterance
from harness.persistence.repositories.types import EvaluationResultCreateData


class EvaluationResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, result: EvaluationResultCreateData) -> EvaluationResult:
        row = EvaluationResult(
            result_id=result.get("result_id") or str(uuid.uuid4()),
            utterance_id=result["utterance_id"],
            test_id=result["test_id"],
            raw_chatbot_response=result.get("raw_chatbot_response"),
            normalized_contract=result.get("normalized_contract"),
            evaluation_agent_id=result.get("evaluation_agent_id"),
            evaluation_verdict=result.get("evaluation_verdict"),
            evaluation_scores=result.get("evaluation_scores"),
            result_metadata=result.get("result_metadata"),
            harness_annotations=result.get("harness_annotations"),
            error_status=result.get("error_status"),
            error_stage=result.get("error_stage"),
            error_details=result.get("error_details"),
            evaluation_timestamp=result["evaluation_timestamp"],
        )
        self._session.add(row)
        self._session.flush()
        return row

    def bulk_create_stubs(
        self, utterance_ids: list[str], agent_id: str | None, timestamp: datetime
    ) -> int:
        """Create cancelled-row stubs for the given utterances (FR-003a)."""
        if not utterance_ids:
            return 0
        test_ids = dict(
            self._session.execute(
                select(Utterance.utterance_id, Utterance.test_id).where(
                    Utterance.utterance_id.in_(utterance_ids)
                )
            ).all()
        )
        rows = [
            {
                "result_id": str(uuid.uuid4()),
                "utterance_id": uid,
                "test_id": test_ids[uid],
                "raw_chatbot_response": None,
                "normalized_contract": None,
                "evaluation_agent_id": agent_id,
                "evaluation_verdict": None,
                "evaluation_scores": None,
                "metadata": None,
                "harness_annotations": None,
                "error_status": ErrorStatus.CANCELLED.value,
                "error_stage": None,
                "error_details": None,
                "evaluation_timestamp": timestamp,
            }
            for uid in utterance_ids
        ]
        self._session.execute(insert(EvaluationResult), rows)
        self._session.flush()
        return len(rows)

    def get_by_utterance(self, utterance_id: str) -> EvaluationResult | None:
        return self._session.scalar(
            select(EvaluationResult).where(
                EvaluationResult.utterance_id == utterance_id
            )
        )

    def get_by_job(self, job_id: str) -> list[EvaluationResult]:
        return list(
            self._session.scalars(
                select(EvaluationResult)
                .join(Utterance, EvaluationResult.utterance_id == Utterance.utterance_id)
                .where(Utterance.job_id == job_id)
            )
        )
