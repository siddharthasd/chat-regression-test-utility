"""EvaluationResultRepository tests: US1 (create/get) + US4 (uniqueness constraint)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from harness.persistence.repositories import (
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)


def _job_with_utterance(db_session):
    job = JobRepository(db_session).create_draft("J", None, "u")
    utt = UtteranceRepository(db_session).bulk_create(
        job.job_id, [{"utterance_text": "x", "test_id": "t1", "row_index": 1}]
    )[0]
    return job, utt


def _result_data(utt, **over):
    base = {
        "utterance_id": utt.utterance_id,
        "test_id": utt.test_id,
        "evaluation_timestamp": datetime.now(UTC),
        "evaluation_verdict": "pass",
        "evaluation_scores": [{"parameter_name": "accuracy", "score": 1, "reasoning": "ok"}],
        "result_metadata": {"note": "fine"},
    }
    base.update(over)
    return base


def test_create_and_get_by_utterance(db_session) -> None:
    _job, utt = _job_with_utterance(db_session)
    repo = EvaluationResultRepository(db_session)
    created = repo.create(_result_data(utt))
    fetched = repo.get_by_utterance(utt.utterance_id)
    assert fetched.result_id == created.result_id
    assert fetched.evaluation_verdict == "pass"
    assert fetched.result_metadata == {"note": "fine"}


def test_get_by_job(db_session) -> None:
    job, utt = _job_with_utterance(db_session)
    EvaluationResultRepository(db_session).create(_result_data(utt))
    assert len(EvaluationResultRepository(db_session).get_by_job(job.job_id)) == 1


def test_unique_constraint_one_result_per_utterance(db_session) -> None:
    _job, utt = _job_with_utterance(db_session)
    repo = EvaluationResultRepository(db_session)
    repo.create(_result_data(utt))
    with pytest.raises(IntegrityError):
        repo.create(_result_data(utt))  # second result for same utterance is refused
