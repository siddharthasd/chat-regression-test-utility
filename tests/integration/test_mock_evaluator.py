"""Bundled mock evaluator service tests (US5, FR-022-027, SC-012)."""

from __future__ import annotations

import contextlib
import threading

import httpx

from harness.evaluator import mock, validate_evaluation_result

_CONTRACT = {"utteranceId": "u-1", "utteranceText": "hi", "testId": "t1"}


@contextlib.contextmanager
def running(mode: str = "ok", dimensions=("relevance", "groundedness"), slow_seconds: int = 5):
    server = mock.make_server(
        port=0, mode=mode, dimensions=list(dimensions), slow_seconds=slow_seconds
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_mock_emits_valid_result() -> None:
    with running() as url:
        resp = httpx.post(url, json=_CONTRACT, timeout=5)
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluationAgentId"] == "mock-evaluator"
    assert body["utteranceId"] == "u-1"
    assert validate_evaluation_result(body, expected_utterance_id="u-1") == []  # FR-023


def test_mock_dimensions_match_configured() -> None:
    with running(dimensions=("relevance",)) as url:
        body = httpx.post(url, json=_CONTRACT, timeout=5).json()
    assert [s["parameter_name"] for s in body["evaluationScores"]] == ["relevance"]


def test_mock_nondeterministic() -> None:
    # SC-012: observably different output across calls on identical input.
    with running() as url:
        a = httpx.post(url, json=_CONTRACT, timeout=5).json()
        b = httpx.post(url, json=_CONTRACT, timeout=5).json()
    scores_a = [s["score"] for s in a["evaluationScores"]]
    scores_b = [s["score"] for s in b["evaluationScores"]]
    assert a["evaluationVerdict"] != b["evaluationVerdict"] or scores_a != scores_b


def test_mode_status500() -> None:
    with running(mode="status500") as url:
        assert httpx.post(url, json=_CONTRACT, timeout=5).status_code == 500


def test_mode_nonconformant() -> None:
    with running(mode="nonconformant") as url:
        body = httpx.post(url, json=_CONTRACT, timeout=5).json()
    assert validate_evaluation_result(body, expected_utterance_id="u-1")  # has problems
