"""Job Detail View Flask UI integration tests (US1/US2/US4/US5/US6). Per-test isolated DB."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from harness.persistence import get_session
from harness.persistence.enums import JobStatus
from harness.persistence.repositories import (
    EvaluationResultRepository,
    JobRepository,
    UtteranceRepository,
)


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
    *, status=JobStatus.COMPLETED, conn_auth=None, dims=None, rows=None,
) -> str:
    rows = rows or []
    with get_session() as session:
        jobs = JobRepository(session)
        job = jobs.create_draft("Detail Job", "a job", "alice")
        job.connector_name = "ConnX"
        job.connector_id = "c1"
        job.connector_endpoint_url = "https://c.test"
        job.connector_auth_descriptor = conn_auth or {"mode": "none"}
        job.connector_timeout_seconds = 30
        job.connector_expects_per_row_password = False
        job.evaluation_agent_name = "EvalX"
        job.evaluation_agent_id = "e1"
        job.evaluator_endpoint_url = "https://e.test"
        job.evaluator_auth_descriptor = {"mode": "none"}
        job.evaluator_timeout_seconds = 60
        job.evaluator_declared_scoring_dimensions = dims or ["relevance", "tone"]
        job.source_csv_filename = "rows.csv"
        job.total_utterance_count = len(rows)

        created = UtteranceRepository(session).bulk_create(
            job.job_id,
            [
                {
                    "utterance_text": r["text"],
                    "test_id": r["test_id"],
                    "row_index": i + 1,
                    "extra_metadata": r.get("extra"),
                }
                for i, r in enumerate(rows)
            ],
        )
        res = EvaluationResultRepository(session)
        processed = failed = 0
        for u, r in zip(created, rows, strict=True):
            if "result" in r:
                res.create(
                    {
                        "utterance_id": u.utterance_id,
                        "test_id": u.test_id,
                        "evaluation_timestamp": datetime.now(UTC),
                        **r["result"],
                    }
                )
                processed += 1
                if r["result"].get("error_status") == "failed":
                    failed += 1
        job.processed_count = processed
        job.failed_count = failed
        job.status = status.value if isinstance(status, JobStatus) else status
        return job.job_id


def _completed_result(text="Hi there", verdict="pass", scores=None, annotations=None):
    return {
        "normalized_contract": {"chatbotResponse": {"normalizedText": text}},
        "raw_chatbot_response": {"echo": text},
        "evaluation_verdict": verdict,
        "evaluation_scores": scores
        or [{"parameter_name": "relevance", "score": 0.9, "reasoning": "good"}],
        "result_metadata": {"m": 1},
        "harness_annotations": annotations,
    }


def _html(client, job_id, qs=""):
    return client.get(f"/jobs/{job_id}/detail{qs}").get_data(as_text=True)


# --------------------------------------------------------------------------- US1
def test_metadata_panel_masks_secrets(client) -> None:
    job_id = _seed(
        conn_auth={"mode": "bearer", "credential": "SECRET-TOK-123"},
        rows=[{"text": "hi", "test_id": "t1", "result": _completed_result()}],
    )
    body = _html(client, job_id)
    assert "SECRET-TOK-123" not in body  # SC-003
    assert "••••••••" in body
    assert "ConnX" in body and "EvalX" in body
    assert "Processed 1" in body


def test_draft_blank_timestamps(client) -> None:
    job_id = _seed(status=JobStatus.DRAFT, rows=[])
    body = _html(client, job_id)
    # started/completed render as the em-dash placeholder, not a date
    assert "Started" in body and "Completed" in body


def test_download_csv_omits_password(client) -> None:
    job_id = _seed(rows=[{"text": "hello", "test_id": "t1", "result": _completed_result()}])
    resp = client.get(f"/jobs/{job_id}/download.csv")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "utteranceText,testId" in text
    assert "password" not in text
    assert "reconstructed" in resp.headers["Content-Disposition"]


def test_download_csv_partial_marker_for_running(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    resp = client.get(f"/jobs/{job_id}/download.csv")
    assert "partial" in resp.headers["Content-Disposition"]
    assert "# partial download" in resp.get_data(as_text=True)


# --------------------------------------------------------------------------- US2
def test_expand_shows_artifacts(client) -> None:
    job_id = _seed(
        rows=[{"text": "hi", "test_id": "t1", "result": _completed_result(text="Bot says hi")}]
    )
    body = _html(client, job_id)
    assert "Raw chatbot response" in body
    assert "Normalized contract" in body
    assert "Bot says hi" in body  # response text rendered


def test_failed_row_shows_error_stage(client) -> None:
    job_id = _seed(
        rows=[{"text": "hi", "test_id": "t1", "result": {
            "error_status": "failed", "error_stage": "connector_normalization",
            "error_details": "bad contract", "raw_chatbot_response": {"x": 1},
        }}],
    )
    body = _html(client, job_id)
    assert "connector_normalization" in body
    assert "bad contract" in body


def test_scores_ordered_and_unexpected_indicator(client) -> None:
    job_id = _seed(
        dims=["relevance", "tone"],
        rows=[{"text": "hi", "test_id": "t1", "result": _completed_result(
            verdict="warn",
            scores=[{"parameter_name": "SURPRISE", "score": 0.1, "reasoning": "x"}],
            annotations={"unexpected_score_dimensions": ["SURPRISE"]},
        )}],
    )
    body = _html(client, job_id)
    assert "evaluator emitted unexpected dimensions" in body
    # declared dims appear as cells even though the evaluator didn't emit them
    assert "relevance:" in body and "tone:" in body
    assert "SURPRISE:" in body


# --------------------------------------------------------------------------- US4
def test_verdict_filter_and_error_only(client) -> None:
    job_id = _seed(rows=[
        {"text": "passrow", "test_id": "t1", "result": _completed_result(verdict="pass")},
        {"text": "failrow", "test_id": "t2", "result": {
            "error_status": "failed", "error_stage": "evaluator_result", "error_details": "x"}},
    ])
    only_fail = _html(client, job_id, "?error_only=1")
    assert "failrow" in only_fail and "passrow" not in only_fail
    only_pass = _html(client, job_id, "?verdict=pass")
    assert "passrow" in only_pass and "failrow" not in only_pass


def test_search_matches_utterance_only(client) -> None:
    job_id = _seed(rows=[
        {"text": "find-me-token", "test_id": "t1", "result": _completed_result()},
        {"text": "other", "test_id": "t2", "result": _completed_result()},
    ])
    body = _html(client, job_id, "?q=find-me-token")
    assert "find-me-token" in body and "other" not in body
    assert "Visible: 1 of 2" in body


def test_scores_column_not_sortable(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _completed_result()}])
    body = _html(client, job_id)
    assert "sort=scores" not in body  # no sort affordance on Scores (FR-011)


# --------------------------------------------------------------------------- US5
def test_detail_json_live_and_terminal(client) -> None:
    running = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    done = _seed(status=JobStatus.COMPLETED, rows=[{"text": "hi", "test_id": "t1",
                                                    "result": _completed_result()}])
    assert client.get(f"/jobs/{running}/detail.json").get_json()["terminal"] is False
    dj = client.get(f"/jobs/{done}/detail.json").get_json()
    assert dj["terminal"] is True and dj["row_count"] == 1


def test_detail_json_404_when_deleted(client) -> None:
    assert client.get("/jobs/nope/detail.json").status_code == 404


# --------------------------------------------------------------------------- US6
def test_cancel_control_visibility(client) -> None:
    for st in (JobStatus.QUEUED, JobStatus.RUNNING):
        assert "Cancel Job" in _html(client, _seed(status=st, rows=[]))
    for st in (JobStatus.DRAFT, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        assert "Cancel Job" not in _html(client, _seed(status=st, rows=[]))


def test_delete_control_visibility(client) -> None:
    for st in (JobStatus.DRAFT, JobStatus.FAILED, JobStatus.CANCELLED):
        assert "Delete Job" in _html(client, _seed(status=st, rows=[]))
    for st in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED):
        assert "Delete Job" not in _html(client, _seed(status=st, rows=[]))


def test_cancel_transitions_to_cancelling(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[])
    resp = client.post(f"/jobs/{job_id}/cancel")
    assert resp.status_code == 302
    with get_session() as session:
        assert JobRepository(session).get(job_id).status == "cancelling"


def test_cancel_terminal_rejected(client) -> None:
    job_id = _seed(status=JobStatus.COMPLETED, rows=[])
    assert client.post(f"/jobs/{job_id}/cancel").status_code == 409


def test_delete_redirects_to_dashboard(client) -> None:
    job_id = _seed(status=JobStatus.FAILED, rows=[{"text": "hi", "test_id": "t1"}])
    resp = client.post(f"/jobs/{job_id}/delete")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    with get_session() as session:
        assert JobRepository(session).get(job_id) is None


def test_delete_completed_rejected(client) -> None:
    job_id = _seed(status=JobStatus.COMPLETED, rows=[])
    assert client.post(f"/jobs/{job_id}/delete").status_code == 409
