"""Results export Flask UI integration tests (US1-US4). Per-test isolated DB."""

from __future__ import annotations

import csv
import io
import json
import zipfile
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


def _seed(*, status=JobStatus.COMPLETED, conn_auth=None, rows=None) -> str:
    rows = rows or []
    with get_session() as session:
        jobs = JobRepository(session)
        job = jobs.create_draft("Export Job", "d", "alice")
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
        job.evaluator_declared_scoring_dimensions = ["relevance"]
        job.source_csv_filename = "rows.csv"
        job.total_utterance_count = len(rows)
        created = UtteranceRepository(session).bulk_create(
            job.job_id,
            [{"utterance_text": r["text"], "test_id": r["test_id"], "row_index": i + 1}
             for i, r in enumerate(rows)],
        )
        res = EvaluationResultRepository(session)
        processed = failed = 0
        for u, r in zip(created, rows, strict=True):
            if "result" in r:
                res.create({"utterance_id": u.utterance_id, "test_id": u.test_id,
                            "evaluation_timestamp": datetime.now(UTC), **r["result"]})
                processed += 1
                if r["result"].get("error_status") == "failed":
                    failed += 1
        job.processed_count = processed
        job.failed_count = failed
        job.status = status.value if isinstance(status, JobStatus) else status
        return job.job_id


def _ok_result(verdict="pass"):
    return {
        "normalized_contract": {"chatbotResponse": {"normalizedText": "Hi"}},
        "raw_chatbot_response": {"echo": "hi"},
        "evaluation_verdict": verdict,
        "evaluation_scores": [{"parameter_name": "relevance", "score": 0.9, "reasoning": "g"}],
        "result_metadata": {"m": 1},
    }


# --------------------------------------------------------------------------- US1
def test_download_csv(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _ok_result()}])
    resp = client.get(f"/jobs/{job_id}/export?format=csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "results.csv" in resp.headers["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(resp.get_data(as_text=True))))
    assert len(rows) == 1 and rows[0]["jobId"]


def test_download_json(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _ok_result()}])
    resp = client.get(f"/jobs/{job_id}/export?format=json")
    assert resp.mimetype == "application/json"
    data = json.loads(resp.get_data())
    assert set(data) == {"job", "rows", "partial"} and len(data["rows"]) == 1


def test_download_zip(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _ok_result()}])
    resp = client.get(f"/jobs/{job_id}/export?format=zip")
    assert resp.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.get_data())) as zf:
        assert len(zf.namelist()) == 2


def test_control_present_on_detail_page(client) -> None:
    job_id = _seed(rows=[{"text": "hi", "test_id": "t1", "result": _ok_result()}])
    body = client.get(f"/jobs/{job_id}/detail").get_data(as_text=True)
    assert "Download Results" in body
    assert f"/jobs/{job_id}/export" in body


def test_no_secret_in_export(client) -> None:
    job_id = _seed(
        conn_auth={"mode": "bearer", "credential": "TOKEN-XYZ-9"},
        rows=[{"text": "hi", "test_id": "t1", "result": _ok_result()}],
    )
    for fmt in ("csv", "json"):
        assert b"TOKEN-XYZ-9" not in client.get(f"/jobs/{job_id}/export?format={fmt}").get_data()


# --------------------------------------------------------------------------- US2
def test_running_export_is_partial(client) -> None:
    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "hi", "test_id": "t1"}])
    resp = client.get(f"/jobs/{job_id}/export?format=json")
    assert "partial" in resp.headers["Content-Disposition"]
    assert json.loads(resp.get_data())["partial"] is True


# --------------------------------------------------------------------------- US3
def test_reexport_reflects_new_rows(client) -> None:
    from harness.persistence.models import Utterance

    job_id = _seed(status=JobStatus.RUNNING, rows=[{"text": "a", "test_id": "t1"}])
    first = json.loads(client.get(f"/jobs/{job_id}/export?format=json").get_data())
    assert len(first["rows"]) == 1
    # Persist another row directly (bulk_create requires a draft parent; job is running).
    with get_session() as session:
        session.add(
            Utterance(
                utterance_id="u2", job_id=job_id, utterance_text="b", row_index=2, test_id="t2"
            )
        )
    second = json.loads(client.get(f"/jobs/{job_id}/export?format=json").get_data())
    assert len(second["rows"]) == 2  # fresh build picked up the new row (no cache)


# --------------------------------------------------------------------------- US4
def test_failed_job_export_has_error_fields(client) -> None:
    job_id = _seed(status=JobStatus.FAILED, rows=[
        {"text": "hi", "test_id": "t1", "result": {
            "error_status": "failed", "error_stage": "evaluator_result", "error_details": "boom"}},
    ])
    data = json.loads(client.get(f"/jobs/{job_id}/export?format=json").get_data())
    row = data["rows"][0]
    assert row["errorStatus"] == "failed" and row["errorStage"] == "evaluator_result"


def test_draft_has_no_export(client) -> None:
    job_id = _seed(status=JobStatus.DRAFT, rows=[])
    assert client.get(f"/jobs/{job_id}/export?format=csv").status_code == 400
    body = client.get(f"/jobs/{job_id}/detail").get_data(as_text=True)
    assert "Download Results" not in body


def test_queued_job_export_rejected(client) -> None:
    job_id = _seed(status=JobStatus.QUEUED, rows=[{"text": "hi", "test_id": "t1"}])
    assert client.get(f"/jobs/{job_id}/export?format=csv").status_code == 400


def test_deleted_job_export_404(client) -> None:
    assert client.get("/jobs/ghost/export?format=csv").status_code == 404
