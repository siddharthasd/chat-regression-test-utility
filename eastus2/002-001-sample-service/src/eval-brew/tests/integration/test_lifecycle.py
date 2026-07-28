"""End-to-end lifecycle + durability integration tests (US1, US4).

Covers SC-001 (full lifecycle counts), SC-005 (credentials encrypted on disk),
SC-008 (crash mid-transaction atomicity), and FR-022 (orphaned-running query).
"""

from __future__ import annotations

from datetime import UTC, datetime

from harness.persistence import get_session, init_db
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    EvaluationAgentRegistrationRepository,
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)


def _connector(session):
    return ConnectorRegistrationRepository(session).create(
        {
            "display_name": "Conn",
            "endpoint_url": "https://conn.test",
            "auth_descriptor": {"mode": "bearer", "credential": "TOK"},
        }
    )


def _evaluator(session):
    return EvaluationAgentRegistrationRepository(session).create(
        {
            "display_name": "Eval",
            "description": "d",
            "endpoint_url": "https://eval.test",
            "auth_descriptor": {"mode": "none"},
        }
    )


def _snapshotted_draft(session, jobs):
    job = jobs.create_draft("Run", None, "alice")
    jobs.set_connector_snapshot(job.job_id, _connector(session))
    jobs.set_evaluator_snapshot(job.job_id, _evaluator(session))
    return job


def test_full_lifecycle(db_session) -> None:
    jobs = JobRepository(db_session)
    utterances = UtteranceRepository(db_session)
    results = EvaluationResultRepository(db_session)

    job = _snapshotted_draft(db_session, jobs)
    rows = [
        {"utterance_text": f"u{i}", "test_id": f"t{i}", "row_index": i}
        for i in range(1, 6)
    ]
    created = utterances.bulk_create(job.job_id, rows)
    jobs.set_csv_metadata(job.job_id, "in.csv", len(created))

    jobs.transition_to_queued(job.job_id)
    jobs.transition_to_running(job.job_id)

    for idx, utt in enumerate(created):
        failed = idx == 4  # last row fails
        results.create(
            {
                "utterance_id": utt.utterance_id,
                "test_id": utt.test_id,
                "evaluation_timestamp": datetime.now(UTC),
                "error_status": "failed" if failed else None,
                "error_stage": "connector_transport" if failed else None,
                "evaluation_verdict": None if failed else "pass",
            }
        )
        jobs.increment_processed_count(job.job_id)
        if failed:
            jobs.increment_failed_count(job.job_id)

    jobs.transition_to_completed(job.job_id)

    final = jobs.get(job.job_id)
    assert final.status == JobStatus.COMPLETED
    assert final.total_utterance_count == 5
    assert final.processed_count == 5
    assert final.failed_count == 1
    assert utterances.count_by_job(job.job_id) == 5
    assert len(results.get_by_job(job.job_id)) == 5


def test_crash_mid_transaction_rolls_back_both_writes(db_session) -> None:
    jobs = JobRepository(db_session)
    job = jobs.create_draft("J", None, "u")
    utt = UtteranceRepository(db_session).bulk_create(
        job.job_id, [{"utterance_text": "x", "test_id": "t1", "row_index": 1}]
    )[0]

    try:
        with db_session.begin_nested():
            EvaluationResultRepository(db_session).create(
                {
                    "utterance_id": utt.utterance_id,
                    "test_id": "t1",
                    "evaluation_timestamp": datetime.now(UTC),
                }
            )
            jobs.increment_processed_count(job.job_id)
            raise RuntimeError("simulated crash")
    except RuntimeError:
        pass

    db_session.expire_all()
    assert EvaluationResultRepository(db_session).get_by_utterance(utt.utterance_id) is None
    assert jobs.get(job.job_id).processed_count == 0


def test_orphaned_running_job_is_queryable(db_session) -> None:
    jobs = JobRepository(db_session)
    job = _snapshotted_draft(db_session, jobs)
    jobs.transition_to_queued(job.job_id)
    jobs.transition_to_running(job.job_id)
    running = jobs.get_by_status(JobStatus.RUNNING.value)
    assert job.job_id in {j.job_id for j in running}


def test_credentials_encrypted_on_disk(tmp_path) -> None:
    secret = "DISTINCTIVE-CRED-ABC987"
    engine = init_db(tmp_path / "data.db")
    try:
        with get_session() as session:
            jobs = JobRepository(session)
            reg = ConnectorRegistrationRepository(session).create(
                {
                    "display_name": "C",
                    "endpoint_url": "https://c",
                    "auth_descriptor": {"mode": "bearer", "credential": secret},
                }
            )
            job = jobs.create_draft("J", None, "u")
            jobs.set_connector_snapshot(job.job_id, reg)
    finally:
        engine.dispose()

    blob = b"".join(p.read_bytes() for p in tmp_path.glob("data.db*"))
    assert secret.encode() not in blob
