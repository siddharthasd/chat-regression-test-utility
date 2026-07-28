"""Dashboard Flask UI integration tests (US1-US5 + cleanup). Per-test isolated DB."""

from __future__ import annotations

import os

import pytest

from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import JobRepository


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_KEY_FILE", str(tmp_path / "ui.key"))
    from harness.persistence import encryption, engine

    encryption._reset_key_cache_for_tests()
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — integration tests require PostgreSQL")
    engine.init_db()
    from harness.ui import create_app
    from starlette.testclient import TestClient

    return TestClient(create_app(), raise_server_exceptions=True, follow_redirects=False)


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


def _html(client, path="/jobs"):
    return client.get(path).text


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
    body = _html(client, "/jobs?status=running")
    assert "RunOnly" in body and "DoneOnly" not in body


def test_connector_filter_and_search_combine(client) -> None:
    _seed(name="Alpha", connector="ConnA")
    _seed(name="Beta", connector="ConnB")
    _seed(name="AlphaTwo", connector="ConnA")
    # connector=ConnA AND name search "Two"
    body = _html(client, "/jobs?connector=ConnA&q=Two")
    assert "AlphaTwo" in body
    assert "Beta" not in body
    assert ">Alpha<" not in body  # 'Alpha' (ConnA but no 'Two') filtered out


def test_created_by_filter(client) -> None:
    _seed(name="ByAlice", created_by="alice")
    _seed(name="ByBob", created_by="bob")
    body = _html(client, "/jobs?created_by=bob")
    assert "ByBob" in body and "ByAlice" not in body


def test_sort_by_name_ascending(client) -> None:
    _seed(name="Zeta")
    _seed(name="Alpha")
    body = _html(client, "/jobs?sort=job_name&dir=asc")
    assert body.index("Alpha") < body.index("Zeta")


def test_no_matches_state_distinct_from_empty(client) -> None:
    _seed(status=JobStatus.RUNNING, name="OnlyRunning")
    body = _html(client, "/jobs?status=completed")
    assert "No jobs match the current filters" in body
    assert "No jobs yet" not in body


# --------------------------------------------------------------------------- US5
def test_jobs_json_live_state(client) -> None:
    _seed(status=JobStatus.RUNNING, name="Live", processed=4, total=10, failed=1)
    _seed(status=JobStatus.COMPLETED, name="Done")
    data = client.get("/dashboard/jobs.json").json()
    by_status = {j["status"]: j for j in data["jobs"]}
    assert by_status["running"]["terminal"] is False
    assert by_status["running"]["processed"] == 4 and by_status["running"]["total"] == 10
    assert by_status["completed"]["terminal"] is True


# --------------------------------------------------------------------------- Cleanup
def test_delete_failed_job(client) -> None:
    job_id = _seed(status=JobStatus.FAILED, name="ToDelete")
    resp = client.post(f"/dashboard/jobs/{job_id}/delete")
    assert resp.status_code in (302, 303)
    assert "ToDelete" not in _html(client)


def test_delete_completed_no_errors_has_no_delete_button(client) -> None:
    """Completed jobs with no failed rows have no Delete button shown in the UI."""
    job_id = _seed(status=JobStatus.COMPLETED, name="CleanDone", failed=0)
    body = _html(client)
    assert f"/dashboard/jobs/{job_id}/delete" not in body


def test_delete_completed_with_errors_has_delete_button(client) -> None:
    """Completed-with-errors jobs show a Delete button and can be individually removed."""
    job_id = _seed(status=JobStatus.COMPLETED, name="ErrorDone", failed=3)
    body = _html(client)
    assert f"/dashboard/jobs/{job_id}/delete" in body
    resp = client.post(f"/dashboard/jobs/{job_id}/delete")
    assert resp.status_code in (302, 303)
    assert "ErrorDone" not in _html(client)


def test_delete_control_only_on_terminal_error_rows(client) -> None:
    fail_id = _seed(status=JobStatus.FAILED, name="FailedJob")
    comp_err_id = _seed(status=JobStatus.COMPLETED, name="CompletedWithErrors", failed=2)
    run_id = _seed(status=JobStatus.RUNNING, name="RunningJob")
    clean_id = _seed(status=JobStatus.COMPLETED, name="CleanCompleted", failed=0)
    body = _html(client)
    assert f"/dashboard/jobs/{fail_id}/delete" in body
    assert f"/dashboard/jobs/{comp_err_id}/delete" in body
    assert f"/dashboard/jobs/{run_id}/delete" not in body
    assert f"/dashboard/jobs/{clean_id}/delete" not in body


def test_clear_terminal_removes_failed_cancelled_and_completed_with_errors(client) -> None:
    _seed(status=JobStatus.FAILED, name="FailedJobToDelete")
    _seed(status=JobStatus.CANCELLED, name="CancelledJobToDelete")
    _seed(status=JobStatus.COMPLETED, name="CompletedWithErrorsToDelete", failed=5)
    _seed(status=JobStatus.COMPLETED, name="CleanCompletedToKeep", failed=0)
    _seed(status=JobStatus.RUNNING, name="RunningJobToKeep")
    assert client.post("/dashboard/clear-terminal").status_code in (302, 303)
    body = _html(client)
    assert "FailedJobToDelete" not in body
    assert "CancelledJobToDelete" not in body
    assert "CompletedWithErrorsToDelete" not in body
    assert "CleanCompletedToKeep" in body
    assert "RunningJobToKeep" in body
