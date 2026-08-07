"""Job Detail View Flask UI integration tests (US1/US2/US4/US5/US6). Per-test isolated DB."""

from __future__ import annotations

import os
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
    return client.get(f"/jobs/{job_id}/detail{qs}").text


# --------------------------------------------------------------------------- US1
def test_metadata_panel_masks_secrets(client) -> None:
    job_id = _seed(
        conn_auth={"mode": "bearer", "credential": "SECRET-TOK-123"},
        rows=[{"text": "hi", "test_id": "t1", "result": _completed_result()}],
    )
    body = _html(client, job_id)
    assert "SECRET-TOK-123" not in body  # SC-003 — secret must never leak
    assert "bearer" in body              # mode is shown; credential value is omitted entirely
    assert "ConnX" in body and "EvalX" in body
    assert "Processed 1" in body


def test_draft_blank_timestamps(client) -> None:
    job_id = _seed(status=JobStatus.DRAFT, rows=[])
    body = _html(client, job_id)
    # started/completed render as the em-dash placeholder, not a date
    assert "Started" in body and "Completed" in body


def test_download_results_csv_terminal(client) -> None:
    job_id = _seed(rows=[{"text": "hello", "test_id": "t1", "result": _completed_result()}])
    resp = client.get(f"/jobs/{job_id}/download-results.csv")
    assert resp.status_code == 200
    text = resp.text
    header = text.splitlines()[0]
    assert header == (
        "utteranceText,testId,utteranceIntent,chatbotResponse,overallVerdict,"
        "parameterName,score,verdict,reasoning,sourceIndex,title,url,documentId,scope,chunk"
    )
    assert "password" not in text
    assert "results.csv" in resp.headers["Content-Disposition"]


def test_download_results_csv_running_returns_404(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    assert client.get(f"/jobs/{job_id}/download-results.csv").status_code == 404


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
        {"text": "zzz-no-match-row", "test_id": "t2", "result": _completed_result()},
    ])
    body = _html(client, job_id, "?q=find-me-token")
    assert "find-me-token" in body and "zzz-no-match-row" not in body
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
    assert client.get(f"/jobs/{running}/detail.json").json()["terminal"] is False
    dj = client.get(f"/jobs/{done}/detail.json").json()
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
    assert resp.status_code in (302, 303)
    with get_session() as session:
        assert JobRepository(session).get(job_id).status == "cancelling"


def test_cancel_terminal_rejected(client) -> None:
    job_id = _seed(status=JobStatus.COMPLETED, rows=[])
    assert client.post(f"/jobs/{job_id}/cancel").status_code == 409


def test_delete_redirects_to_dashboard(client) -> None:
    job_id = _seed(status=JobStatus.FAILED, rows=[{"text": "hi", "test_id": "t1"}])
    resp = client.post(f"/jobs/{job_id}/delete")
    assert resp.status_code in (302, 303) and resp.headers["Location"].endswith("/")
    with get_session() as session:
        assert JobRepository(session).get(job_id) is None


def test_delete_completed_rejected(client) -> None:
    job_id = _seed(status=JobStatus.COMPLETED, rows=[])
    assert client.post(f"/jobs/{job_id}/delete").status_code == 409


# --------------------------------------------------------------------------- 018 Analytics
def _v2_result(verdict="pass", scores=None):
    return {
        "normalized_contract": {"chatbotResponse": {"normalizedText": "hi"}},
        "raw_chatbot_response": {"echo": "hi"},
        "evaluation_verdict": verdict,
        "evaluation_scores": scores or [
            {"parameter_name": "relevance", "score": 0.9, "reasoning": "good", "verdict": "pass"},
            {"parameter_name": "tone", "score": 0.8, "reasoning": "ok", "verdict": "pass"},
        ],
        "result_metadata": {},
    }


def test_analytics_tiles_visible_for_completed_job(client) -> None:
    job_id = _seed(
        rows=[
            {"text": "hi", "test_id": "t1", "result": _v2_result()},
            {"text": "hello", "test_id": "t2", "result": _v2_result(verdict="fail")},
        ]
    )
    body = _html(client, job_id)
    assert "Overall Mean Score" in body
    assert "Overall Verdict Distribution" in body
    assert "Parameter Breakdown" in body


def test_analytics_skipped_for_large_job(client) -> None:
    job_id = _seed(
        rows=[{"text": "hi", "test_id": "t1", "result": _v2_result()}],
    )
    # Override total_utterance_count to simulate >5000
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        job.total_utterance_count = 5001
    body = _html(client, job_id)
    assert "more than 5,000 utterances" in body
    assert "analytics report is skipped" in body


def test_analytics_empty_state_for_all_errors(client) -> None:
    job_id = _seed(
        rows=[{"text": "hi", "test_id": "t1", "result": {
            "error_status": "failed", "error_stage": "connector", "error_details": "err",
        }}]
    )
    body = _html(client, job_id)
    assert "No evaluated results" in body


def test_download_results_json_terminal(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _v2_result()}])
    resp = client.get(f"/jobs/{job_id}/download-results.json")
    assert resp.status_code == 200
    assert "results.json" in resp.headers["Content-Disposition"]
    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["utteranceText"] == "hi"
    assert "parameters" in data[0]


def test_download_results_json_running_returns_404(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    assert client.get(f"/jobs/{job_id}/download-results.json").status_code == 404


def test_v1_verdict_omitted_from_json(client) -> None:
    v1_result = {
        "normalized_contract": {"chatbotResponse": {"normalizedText": "hi"}},
        "raw_chatbot_response": {"echo": "hi"},
        "evaluation_verdict": "pass",
        "evaluation_scores": [
            {"parameter_name": "relevance", "score": 0.9, "reasoning": "good"},
        ],
        "result_metadata": {},
    }
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": v1_result}])
    resp = client.get(f"/jobs/{job_id}/download-results.json")
    data = resp.json()
    # v1: no "verdict" key in the scores dict → omitted from JSON (not null)
    assert "verdict" not in data[0]["parameters"][0]


def test_old_download_csv_route_removed(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _v2_result()}])
    assert client.get(f"/jobs/{job_id}/download.csv").status_code == 404


def test_sidebar_nav_present(client) -> None:
    job_id = _seed(
        rows=[{"text": "hi", "test_id": "t1", "result": _v2_result()}]
    )
    body = _html(client, job_id)
    assert "sidebar-nav" in body
    assert "section-job-overview" in body
    assert "section-parameter-breakdown" in body
    assert "section-result-explorer" in body


# --------------------------------------------------------------------------- BL-001 XLSX
def _result_with_sources(sources=None):
    return {
        "normalized_contract": {
            "chatbotResponse": {
                "normalizedText": "Hi",
                "metadata": {"sources": sources or []},
            }
        },
        "raw_chatbot_response": {},
        "evaluation_verdict": "pass",
        "evaluation_scores": [
            {"parameter_name": "relevance", "score": 0.9, "reasoning": "ok", "verdict": "pass"},
        ],
        "result_metadata": {},
    }


def test_download_results_xlsx_terminal(client) -> None:
    import io
    import openpyxl

    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _result_with_sources()}])
    resp = client.get(f"/jobs/{job_id}/download-results.xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["Content-Type"]
    assert "results.xlsx" in resp.headers["Content-Disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Results", "Retrieved Sources", "Data Dictionary"]


def test_download_results_xlsx_running_returns_404(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    assert client.get(f"/jobs/{job_id}/download-results.xlsx").status_code == 404


def test_download_results_xlsx_unknown_job_returns_404(client) -> None:
    assert client.get("/jobs/does-not-exist/download-results.xlsx").status_code == 404


def test_download_results_xlsx_sources_in_sheet2(client) -> None:
    import io
    import openpyxl

    sources = [
        {"url": "https://kb/1", "title": "Art1", "chunk": "text1", "scope": "hr", "documentId": "d1"},
        {"url": "https://kb/2", "title": "Art2", "chunk": "text2", "scope": "hr", "documentId": "d2"},
    ]
    job_id = _seed(rows=[{
        "text": "hi", "test_id": "t1",
        "result": _result_with_sources(sources=sources),
    }])
    resp = client.get(f"/jobs/{job_id}/download-results.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws2 = wb["Retrieved Sources"]
    # header + 2 source rows
    assert ws2.max_row == 3
    row_vals = [list(r) for r in ws2.iter_rows(min_row=2, values_only=True)]
    assert row_vals[0][3] == 1   # sourceIndex
    assert row_vals[1][3] == 2
    assert row_vals[0][4] == "Art1"  # title


def test_v2_verdict_in_scores_cells(client) -> None:
    job_id = _seed(
        dims=["relevance"],
        rows=[{"text": "hi", "test_id": "t1", "result": {
            "normalized_contract": {"chatbotResponse": {"normalizedText": "hi"}},
            "raw_chatbot_response": {},
            "evaluation_verdict": "pass",
            "evaluation_scores": [
                {"parameter_name": "relevance", "score": 0.9, "reasoning": "x", "verdict": "pass"}
            ],
            "result_metadata": {},
        }}],
    )
    body = _html(client, job_id)
    # v2 verdict rendered in the scores cells as [pass]
    assert "[pass]" in body


# --------------------------------------------------------------------------- BL-002 Flat downloads

def _completed_result_with_sources(text="Answer", sources=None):
    return {
        "normalized_contract": {
            "chatbotResponse": {
                "normalizedText": text,
                "metadata": {"sources": sources or []},
            }
        },
        "raw_chatbot_response": {"echo": text},
        "evaluation_verdict": "pass",
        "evaluation_scores": [
            {"parameter_name": "relevance", "score": 0.9, "reasoning": "good", "verdict": "pass"},
            {"parameter_name": "tone", "score": 0.8, "reasoning": "fine", "verdict": "pass"},
        ],
        "result_metadata": {},
    }


def test_download_results_flat_csv_terminal(client) -> None:
    sources = [
        {"url": "https://kb/1", "title": "Art1", "chunk": "c1", "scope": "hr", "documentId": "d1"},
    ]
    job_id = _seed(
        dims=["relevance", "tone"],
        rows=[{"text": "Q1", "test_id": "t1", "result": _completed_result_with_sources(sources=sources)}],
    )
    resp = client.get(f"/jobs/{job_id}/download-results-flat.csv")
    assert resp.status_code == 200
    assert "results-flat.csv" in resp.headers["Content-Disposition"]
    header = resp.text.splitlines()[0]
    for col in ("utteranceText", "testId", "relevance_score", "relevance_verdict",
                "tone_score", "source1_title", "source1_url"):
        assert col in header, f"Missing column: {col}"
    import csv as csv_mod
    rows = list(csv_mod.DictReader(resp.text.splitlines()))
    assert len(rows) == 1
    assert rows[0]["utteranceText"] == "Q1"
    assert rows[0]["relevance_score"] == "0.9"
    assert rows[0]["source1_title"] == "Art1"


def test_download_results_flat_csv_running_returns_404(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    assert client.get(f"/jobs/{job_id}/download-results-flat.csv").status_code == 404


def test_download_results_flat_xlsx_terminal(client) -> None:
    import io as _io
    import openpyxl as _openpyxl
    sources = [
        {"url": "https://kb/1", "title": "Art1", "chunk": "c1", "scope": "hr", "documentId": "d1"},
    ]
    job_id = _seed(
        dims=["relevance", "tone"],
        rows=[{"text": "Q1", "test_id": "t1", "result": _completed_result_with_sources(sources=sources)}],
    )
    resp = client.get(f"/jobs/{job_id}/download-results-flat.xlsx")
    assert resp.status_code == 200
    assert "results-flat.xlsx" in resp.headers["Content-Disposition"]
    wb = _openpyxl.load_workbook(_io.BytesIO(resp.content))
    assert "Results (Flat)" in wb.sheetnames
    assert "Data Dictionary" in wb.sheetnames
    ws = wb["Results (Flat)"]
    # header row + 1 utterance row
    assert ws.max_row == 2
    header_vals = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    assert "utteranceText" in header_vals
    assert "relevance_score" in header_vals
    assert "source1_title" in header_vals


def test_download_results_flat_xlsx_running_returns_404(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    assert client.get(f"/jobs/{job_id}/download-results-flat.xlsx").status_code == 404
