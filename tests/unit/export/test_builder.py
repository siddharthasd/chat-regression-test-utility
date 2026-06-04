"""Results export builder unit tests (005). SimpleNamespace stand-ins — no DB."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

from harness.export import build_export
from harness.export.builder import build_csv, job_metadata, row_record


def _job(*, status="completed", conn_auth=None, dims=None):
    return SimpleNamespace(
        job_id="job-1234abcd",
        job_name="My Run",
        description="d",
        created_by="alice",
        created_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 6, 1, 12, 1, tzinfo=UTC),
        completed_at=datetime(2026, 6, 1, 12, 5, tzinfo=UTC),
        status=status,
        harness_version="0.1.0",
        source_csv_filename="rows.csv",
        error_details=None,
        connector_id="c1",
        connector_name="ConnX",
        connector_endpoint_url="https://c.test",
        connector_auth_descriptor=conn_auth or {"mode": "none"},
        connector_timeout_seconds=30,
        connector_expects_per_row_password=False,
        evaluation_agent_id="e1",
        evaluation_agent_name="EvalX",
        evaluator_endpoint_url="https://e.test",
        evaluator_auth_descriptor={"mode": "none"},
        evaluator_timeout_seconds=60,
        evaluator_declared_scoring_dimensions=dims or ["relevance", "tone"],
        total_utterance_count=1,
        processed_count=1,
        failed_count=0,
    )


def _utt(*, result=None):
    return SimpleNamespace(
        utterance_id="u1", row_index=1, utterance_text="hi, there\nline2", test_id="t1",
        evaluation_result=result,
    )


def _result(scores=None, **over):
    base = dict(
        raw_chatbot_response={"echo": "hi"},
        normalized_contract={"chatbotResponse": {"normalizedText": "Hello"}},
        evaluation_verdict="pass",
        evaluation_scores=scores
        or [{"parameter_name": "relevance", "score": 0.9, "reasoning": "g"}],
        result_metadata={"m": 1},
        harness_annotations={},
        evaluation_agent_id="e1",
        error_status=None,
        error_stage=None,
        error_details=None,
        evaluation_timestamp=datetime(2026, 6, 1, 12, 3, tzinfo=UTC),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_json_shape_and_native_nesteds() -> None:
    job, utts = _job(), [_utt(result=_result())]
    _, mime, body = build_export(job, utts, "json")
    assert mime == "application/json"
    data = json.loads(body)
    assert set(data) == {"job", "rows", "partial"}
    assert len(data["rows"]) == 1
    assert data["rows"][0]["normalizedContract"]["chatbotResponse"]["normalizedText"] == "Hello"
    assert data["rows"][0]["evaluationScores"][0]["parameter_name"] == "relevance"
    assert "password" not in data["rows"][0]


def test_csv_rectangular_repeated_metadata_and_lossless_nesteds() -> None:
    job, utts = _job(), [_utt(result=_result())]
    _, mime, body = build_export(job, utts, "csv")
    assert mime == "text/csv"
    reader = csv.DictReader(io.StringIO(body.decode("utf-8")))
    rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    assert row["jobId"] == "job-1234abcd"  # metadata repeated on the data row
    assert row["utteranceId"] == "u1"
    assert row["utteranceText"] == "hi, there\nline2"  # lossless embedded newline
    assert json.loads(row["evaluationScores"])[0]["score"] == 0.9  # nested JSON in a cell
    assert "password" not in reader.fieldnames


def test_credentials_masked_no_plaintext() -> None:
    job = _job(conn_auth={"mode": "bearer", "credential": "SUPERSECRET"})
    utts = [_utt(result=_result())]
    meta = job_metadata(job, datetime.now(UTC))
    assert meta["connectorAuthDescriptor"]["credential"] == "•" * 8
    for fmt in ("csv", "json"):
        _, _, body = build_export(job, utts, fmt)
        assert b"SUPERSECRET" not in body  # SC-005


def test_scores_ordered_by_declared_then_unexpected() -> None:
    dims = ["alpha", "beta"]
    scores = [
        {"parameter_name": "beta", "score": 2, "reasoning": ""},
        {"parameter_name": "SURPRISE", "score": 9, "reasoning": ""},
        {"parameter_name": "alpha", "score": 1, "reasoning": ""},
    ]
    rec = row_record(_utt(result=_result(scores=scores)), dims)
    names = [s["parameter_name"] for s in rec["evaluationScores"]]
    assert names == ["alpha", "beta", "SURPRISE"]


def test_zip_contains_both_files() -> None:
    job, utts = _job(), [_utt(result=_result())]
    filename, mime, body = build_export(job, utts, "zip")
    assert mime == "application/zip" and filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = zf.namelist()
    assert any(n.endswith(".csv") for n in names)
    assert any(n.endswith(".json") for n in names)


def test_partial_flag_for_running_job() -> None:
    job = _job(status="running")
    filename, _, body = build_export(job, [_utt(result=_result())], "json")
    assert "partial" in filename
    assert json.loads(body)["partial"] is True


def test_failed_row_carries_error_fields() -> None:
    result = _result(
        evaluation_verdict=None, evaluation_scores=None,
        error_status="failed", error_stage="evaluator_result", error_details="boom",
    )
    rec = row_record(_utt(result=result), ["relevance"])
    assert rec["errorStatus"] == "failed"
    assert rec["errorStage"] == "evaluator_result"
    assert rec["errorDetails"] == "boom"


def test_harness_annotations_always_present() -> None:
    rec = row_record(_utt(result=_result()), ["relevance"])
    assert rec["harnessAnnotations"] == {}  # present even when empty (FR-006)


def test_invalid_format_defaults_to_csv() -> None:
    _, mime, _ = build_export(_job(), [_utt(result=_result())], "xml")
    assert mime == "text/csv"


def test_csv_header_only_when_no_rows() -> None:
    # defensive: builder must not crash on zero rows
    body = build_csv(job_metadata(_job(), datetime.now(UTC)), [])
    assert b"utteranceId" in body
