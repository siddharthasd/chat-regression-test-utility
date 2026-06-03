"""UtteranceRepository tests: US1 (bulk create, ordering, count) + US2 (immutability)."""

from __future__ import annotations

import pytest

from harness.persistence.exceptions import UtteranceImmutableError
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    JobRepository,
    UtteranceRepository,
)

_ROWS = [
    {"utterance_text": "first", "test_id": "t1", "row_index": 1},
    {"utterance_text": "second", "test_id": "t2", "row_index": 2, "extra_metadata": {"k": "v"}},
]


def _draft(db_session):
    return JobRepository(db_session).create_draft("J", None, "u")


def test_bulk_create_assigns_ids_and_count(db_session) -> None:
    job = _draft(db_session)
    repo = UtteranceRepository(db_session)
    created = repo.bulk_create(job.job_id, _ROWS)
    assert all(u.utterance_id for u in created)
    assert repo.count_by_job(job.job_id) == 2


def test_get_by_job_ordered_by_row_index(db_session) -> None:
    job = _draft(db_session)
    repo = UtteranceRepository(db_session)
    repo.bulk_create(
        job.job_id,
        [
            {"utterance_text": "b", "test_id": "t", "row_index": 2},
            {"utterance_text": "a", "test_id": "t", "row_index": 1},
        ],
    )
    ordered = repo.get_by_job_ordered(job.job_id)
    assert [u.row_index for u in ordered] == [1, 2]
    assert ordered[1].extra_metadata is None


def test_extra_metadata_preserved(db_session) -> None:
    job = _draft(db_session)
    repo = UtteranceRepository(db_session)
    repo.bulk_create(job.job_id, _ROWS)
    second = repo.get_by_job_ordered(job.job_id)[1]
    assert second.extra_metadata == {"k": "v"}


def test_immutability_bulk_create_refused_past_draft(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    jobs.set_connector_snapshot(
        job.job_id,
        ConnectorRegistrationRepository(db_session).create(
            {"display_name": "C", "endpoint_url": "https://c", "auth_descriptor": {"mode": "none"}}
        ),
    )
    jobs.set_evaluator_snapshot(
        job.job_id,
        EvaluationAgentRegistrationRepository(db_session).create(
            {
                "display_name": "E",
                "description": "d",
                "endpoint_url": "https://e",
                "auth_descriptor": {"mode": "none"},
            }
        ),
    )
    jobs.transition_to_queued(job.job_id)
    with pytest.raises(UtteranceImmutableError):
        UtteranceRepository(db_session).bulk_create(job.job_id, _ROWS)


def test_delete_by_job_only_when_draft(db_session) -> None:
    job = _draft(db_session)
    repo = UtteranceRepository(db_session)
    repo.bulk_create(job.job_id, _ROWS)
    assert repo.delete_by_job(job.job_id) == 2
    assert repo.count_by_job(job.job_id) == 0
