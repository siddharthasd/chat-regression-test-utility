"""Orchestrator end-to-end tests against the bundled mock connector/evaluator.

Covers US1 (happy path), US2 (per-row failure isolation), US3 (cancel), US4
(orphan reconciliation), US5 (concurrency), US6 (empty-store pre-row gate).
Each test gets an isolated DB (per-test init_db) + a fresh password store.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager

import pytest

from harness import password_store
from harness.connector import mock as conn_mock
from harness.evaluator import mock as ev_mock
from harness.orchestrator import enqueue_job, reconcile_orphans, run_job
from harness.persistence import get_session
from harness.persistence.repositories import (
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)


@pytest.fixture
def db(monkeypatch):
    from harness.persistence import engine

    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    password_store._reset_for_tests()
    yield
    password_store._reset_for_tests()


@contextmanager
def _serving(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _make_queued_job(conn_url, eval_url, n, *, expects_password=False, status="queued"):
    with get_session() as session:
        jobs = JobRepository(session)
        job = jobs.create_draft("e2e", None, "tester")
        UtteranceRepository(session).bulk_create(
            job.job_id,
            [
                {"utterance_text": f"u{i}", "test_id": f"t{i}", "row_index": i}
                for i in range(n)
            ],
        )
        job.connector_id = "mock"
        job.connector_endpoint_url = conn_url
        job.connector_auth_descriptor = {"mode": "none"}
        job.connector_timeout_seconds = 30
        job.connector_expects_per_row_password = expects_password
        job.evaluation_agent_id = "mock-evaluator"
        job.evaluator_endpoint_url = eval_url
        job.evaluator_auth_descriptor = {"mode": "none"}
        job.evaluator_timeout_seconds = 60
        job.evaluator_declared_scoring_dimensions = ["mock_dimension_a", "mock_dimension_b"]
        job.total_utterance_count = n
        job.status = status
        session.flush()
        return job.job_id


def _job(job_id):
    with get_session() as session:
        return JobRepository(session).get(job_id)


def _results(job_id):
    with get_session() as session:
        return EvaluationResultRepository(session).get_by_job(job_id)


# --------------------------------------------------------------------------- US1
def test_happy_path_completes(db) -> None:
    with _serving(conn_mock.make_server(mode="ok")) as conn_url, \
         _serving(ev_mock.make_server(mode="ok")) as eval_url:
        job_id = _make_queued_job(conn_url, eval_url, 5)
        run_job(job_id)

    job = _job(job_id)
    assert job.status == "completed"
    assert job.processed_count == 5
    assert job.failed_count == 0
    assert job.completed_at is not None
    results = _results(job_id)
    assert len(results) == 5
    assert all(r.error_status is None and r.evaluation_verdict for r in results)
    assert password_store.job_has_entries(job_id) is False


# --------------------------------------------------------------------------- US2
def test_all_rows_fail_still_completes(db) -> None:
    with _serving(conn_mock.make_server(mode="status500")) as conn_url, \
         _serving(ev_mock.make_server(mode="ok")) as eval_url:
        job_id = _make_queued_job(conn_url, eval_url, 4)
        run_job(job_id)

    job = _job(job_id)
    assert job.status == "completed"  # NOT failed (FR-018)
    assert job.processed_count == 4
    assert job.failed_count == 4
    results = _results(job_id)
    assert len(results) == 4
    assert all(
        r.error_status == "failed" and r.error_stage == "connector_response" for r in results
    )


def test_evaluator_failure_isolated(db) -> None:
    with _serving(conn_mock.make_server(mode="ok")) as conn_url, \
         _serving(ev_mock.make_server(mode="status500")) as eval_url:
        job_id = _make_queued_job(conn_url, eval_url, 3)
        run_job(job_id)

    job = _job(job_id)
    assert job.status == "completed"
    assert job.failed_count == 3
    results = _results(job_id)
    assert all(r.error_stage == "evaluator_response" for r in results)
    # connector succeeded → contract retained on the row
    assert all(r.normalized_contract is not None for r in results)


# --------------------------------------------------------------------------- US3
def test_cancel_mid_run(db) -> None:
    # A slow connector lets us flip the job to cancelling before the loop drains.
    with _serving(conn_mock.make_server(mode="slow", slow_seconds=1)) as conn_url, \
         _serving(ev_mock.make_server(mode="ok")) as eval_url:
        job_id = _make_queued_job(conn_url, eval_url, 6)

        def cancel_soon():
            time.sleep(0.3)
            with get_session() as session:
                JobRepository(session).transition_to_cancelling(job_id)

        canceller = threading.Thread(target=cancel_soon)
        canceller.start()
        run_job(job_id)
        canceller.join(timeout=5)

    job = _job(job_id)
    assert job.status == "cancelled"
    results = _results(job_id)
    assert len(results) == 6  # processed rows + cancelled stubs
    assert any(r.error_status == "cancelled" for r in results)
    assert password_store.job_has_entries(job_id) is False


# --------------------------------------------------------------------------- US4
def test_reconcile_orphans(db) -> None:
    running_id = _make_queued_job("http://x/", "http://y/", 2, status="running")
    cancelling_id = _make_queued_job("http://x/", "http://y/", 2, status="cancelling")

    reconcile_orphans()

    assert _job(running_id).status == "failed"
    assert _job(cancelling_id).status == "failed"
    assert "restarted" in _job(running_id).error_details
    assert _job(running_id).completed_at is not None
    with get_session() as session:
        jobs = JobRepository(session)
        assert jobs.get_by_status("running") == []
        assert jobs.get_by_status("cancelling") == []


# --------------------------------------------------------------------------- US5
@pytest.mark.skipif(sys.platform == "win32", reason="concurrent writer test unreliable on Windows")
def test_two_jobs_concurrent_independent(db) -> None:
    # Drive two run_job workers truly concurrently and join them deterministically
    # (no wall-clock deadline). Servers stay up until both threads finish.
    with _serving(conn_mock.make_server(mode="ok")) as conn_url, \
         _serving(ev_mock.make_server(mode="ok")) as eval_url:
        job_a = _make_queued_job(conn_url, eval_url, 3)
        job_b = _make_queued_job(conn_url, eval_url, 2)

        workers = [
            threading.Thread(target=run_job, args=(job_a,), name="job-a"),
            threading.Thread(target=run_job, args=(job_b,), name="job-b"),
        ]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=30)
        assert not any(w.is_alive() for w in workers), "a worker thread did not finish in time"

    # Independent terminal state + counters.
    assert _job(job_a).status == "completed"
    assert _job(job_b).status == "completed"
    assert _job(job_a).processed_count == 3
    assert _job(job_b).processed_count == 2
    assert _job(job_a).failed_count == 0
    assert _job(job_b).failed_count == 0


def test_enqueue_job_is_async_and_completes(db) -> None:
    # enqueue_job (the production async entry point) must return immediately and
    # the job must reach a terminal state shortly after.
    with _serving(conn_mock.make_server(mode="ok")) as conn_url, \
         _serving(ev_mock.make_server(mode="ok")) as eval_url:
        job_id = _make_queued_job(conn_url, eval_url, 2)

        start = time.monotonic()
        enqueue_job(job_id)
        assert time.monotonic() - start < 1.0  # returns without waiting for the run

        deadline = time.time() + 30
        while time.time() < deadline and _job(job_id).status not in {
            "completed", "failed", "cancelled"
        }:
            time.sleep(0.05)
        assert _job(job_id).status == "completed"
        assert _job(job_id).processed_count == 2


# --------------------------------------------------------------------------- US6
def test_empty_password_store_fails_pre_row(db) -> None:
    job_id = _make_queued_job("http://unused/", "http://unused/", 3, expects_password=True)
    run_job(job_id)  # store is empty for this job

    job = _job(job_id)
    assert job.status == "failed"
    assert "memory" in job.error_details
    assert job.completed_at is not None
    assert _results(job_id) == []  # no pipeline invoked
