"""Dashboard Flask UI integration tests (US1-US5 + cleanup). Per-test isolated DB."""

from __future__ import annotations

import pytest

from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_DB_PATH", str(tmp_path / "ui.db"))
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "ui.key"))
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    engine.init_db(tmp_path / "ui.db")
    from harness.ui import create_app

    return create_app().test_client()


def _seed(
    *, status=JobStatus.DRAFT, name="Job", connector="ConnX", created_by="alice",
    failed=0, processed=0, total=None,
) -> str:
    with get_session() as session:
        job = JobRepository(session).create_draft(name, None, created_by)
        job.status = status.value if isinstance(status, JobStatus) else status
        job.connector_name = connector
        job.failed_count = failed
        job.processed_count = processed
        job.total_utterance_count = total
        return job.job_id


def _html(client, path="/"):
    return client.get(path).get_data(as_text=True)


# --------------------------------------------------------------------------- US1
def test_lists_all_jobs_with_badges(client) -> None:
    _seed(status=JobStatus.DRAFT, name="DraftJob")
    _seed(status=JobStatus.RUNNING, name="RunJob")
    _seed(status=JobStatus.COMPLETED, name="DoneJob")
    _seed(status=JobStatus.FAILED, name="FailJob")
    body = _html(client)
    for n in ("DraftJob", "RunJob", "DoneJob", "FailJob"):
        assert n in body
    assert "badge-draft" in body and "badge-running" in body
    assert "badge-completed" in body and "badge-failed" in body


def test_completed_with_errors_distinction(client) -> None:
    _seed(status=JobStatus.COMPLETED, name="Clean", failed=0)
    _seed(status=JobStatus.COMPLETED, name="Dirty", failed=3)
    body = _html(client)
    assert "Completed with errors" in body
    assert "badge-completed-errors" in body


def test_empty_state_no_jobs(client) -> None:
    body = _html(client)
    assert "No jobs yet" in body
    assert "/jobs/new" in body  # create CTA


# --------------------------------------------------------------------------- US2
def test_create_new_job_link_present_both_states(client) -> None:
    assert "/jobs/new" in _html(client)  # empty state
    _seed(name="Anything")
    assert "/jobs/new" in _html(client)  # populated state


# --------------------------------------------------------------------------- US3
def test_row_links_to_detail(client) -> None:
    job_id = _seed(name="Drill")
    body = _html(client)
    assert f"/jobs/{job_id}/detail" in body
    assert f'data-job-id="{job_id}"' in body


# --------------------------------------------------------------------------- US4
def test_status_filter(client) -> None:
    _seed(status=JobStatus.RUNNING, name="RunOnly")
    _seed(status=JobStatus.COMPLETED, name="DoneOnly")
    body = _html(client, "/?status=running")
    assert "RunOnly" in body and "DoneOnly" not in body


def test_connector_filter_and_search_combine(client) -> None:
    _seed(name="Alpha", connector="ConnA")
    _seed(name="Beta", connector="ConnB")
    _seed(name="AlphaTwo", connector="ConnA")
    # connector=ConnA AND name search "Two"
    body = _html(client, "/?connector=ConnA&q=Two")
    assert "AlphaTwo" in body
    assert "Beta" not in body
    assert ">Alpha<" not in body  # 'Alpha' (ConnA but no 'Two') filtered out


def test_created_by_filter(client) -> None:
    _seed(name="ByAlice", created_by="alice")
    _seed(name="ByBob", created_by="bob")
    body = _html(client, "/?created_by=bob")
    assert "ByBob" in body and "ByAlice" not in body


def test_sort_by_name_ascending(client) -> None:
    _seed(name="Zeta")
    _seed(name="Alpha")
    body = _html(client, "/?sort=job_name&dir=asc")
    assert body.index("Alpha") < body.index("Zeta")


def test_no_matches_state_distinct_from_empty(client) -> None:
    _seed(status=JobStatus.RUNNING, name="OnlyRunning")
    body = _html(client, "/?status=completed")
    assert "No jobs match the current filters" in body
    assert "No jobs yet" not in body


# --------------------------------------------------------------------------- US5
def test_jobs_json_live_state(client) -> None:
    _seed(status=JobStatus.RUNNING, name="Live", processed=4, total=10, failed=1)
    _seed(status=JobStatus.COMPLETED, name="Done")
    data = client.get("/dashboard/jobs.json").get_json()
    by_status = {j["status"]: j for j in data["jobs"]}
    assert by_status["running"]["terminal"] is False
    assert by_status["running"]["processed"] == 4 and by_status["running"]["total"] == 10
    assert by_status["completed"]["terminal"] is True


# --------------------------------------------------------------------------- Cleanup
def test_delete_failed_job(client) -> None:
    job_id = _seed(status=JobStatus.FAILED, name="ToDelete")
    resp = client.post(f"/dashboard/jobs/{job_id}/delete")
    assert resp.status_code == 302
    assert "ToDelete" not in _html(client)


def test_delete_completed_rejected(client) -> None:
    job_id = _seed(status=JobStatus.COMPLETED, name="KeepMe")
    resp = client.post(f"/dashboard/jobs/{job_id}/delete")
    assert resp.status_code == 409
    assert "KeepMe" in _html(client)  # still present


def test_delete_control_only_on_terminal_error_rows(client) -> None:
    fail_id = _seed(status=JobStatus.FAILED, name="Failed")
    run_id = _seed(status=JobStatus.RUNNING, name="Running")
    body = _html(client)
    assert f"/dashboard/jobs/{fail_id}/delete" in body
    assert f"/dashboard/jobs/{run_id}/delete" not in body


def test_clear_terminal_removes_only_failed_and_cancelled(client) -> None:
    _seed(status=JobStatus.FAILED, name="FailedJobToDelete")
    _seed(status=JobStatus.CANCELLED, name="CancelledJobToDelete")
    _seed(status=JobStatus.COMPLETED, name="CompletedJobToKeep")
    _seed(status=JobStatus.RUNNING, name="RunningJobToKeep")
    assert client.post("/dashboard/clear-terminal").status_code == 302
    body = _html(client)
    assert "FailedJobToDelete" not in body and "CancelledJobToDelete" not in body
    assert "CompletedJobToKeep" in body and "RunningJobToKeep" in body
