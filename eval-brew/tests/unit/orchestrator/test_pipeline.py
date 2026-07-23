"""process_row mapping tests (012 US1/US2; FR-011/012, SC-002/008/010).

Uses httpx.MockTransport + injected clients + SimpleNamespace stand-ins for the
Job/Utterance ORM rows, so no DB or network is involved.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from harness import password_store
from harness.connector import mock as conn_mock
from harness.evaluator import mock as ev_mock
from harness.orchestrator.pipeline import process_row

DIMS = ["mock_dimension_a", "mock_dimension_b"]


@pytest.fixture(autouse=True)
def _clean_store():
    password_store._reset_for_tests()
    yield
    password_store._reset_for_tests()


def _job(*, expects_password: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job1",
        connector_id="mock",
        connector_endpoint_url="http://connector/",
        connector_auth_descriptor={"mode": "none"},
        connector_timeout_seconds=30,
        connector_expects_per_row_password=expects_password,
        evaluation_agent_id="mock-evaluator",
        evaluator_endpoint_url="http://evaluator/",
        evaluator_auth_descriptor={"mode": "none"},
        evaluator_timeout_seconds=60,
        evaluator_declared_scoring_dimensions=DIMS,
    )


def _utterance() -> SimpleNamespace:
    return SimpleNamespace(utterance_id="utt1", test_id="t1", utterance_text="hello")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_connector(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(200, json=conn_mock.build_contract(body["testId"], body["utteranceText"]))


def _ok_evaluator(request: httpx.Request) -> httpx.Response:
    contract = json.loads(request.content)
    return httpx.Response(200, json=ev_mock.build_result(contract["utteranceId"], DIMS))


# --------------------------------------------------------------------------- US1
def test_success_mapping() -> None:
    data = process_row(
        _job(), _utterance(),
        conn_client=_client(_ok_connector), eval_client=_client(_ok_evaluator),
    )
    assert data.get("error_status") is None
    assert data["evaluation_verdict"] in {"pass", "fail", "warn"}
    assert data["evaluation_scores"] is not None
    assert data["evaluation_agent_id"] == "mock-evaluator"
    assert data["normalized_contract"]["testId"] == "t1"
    assert data["raw_chatbot_response"] == {"echo": "hello"}
    assert data["harness_annotations"] == {"unexpected_score_dimensions": []}


def test_password_looked_up_and_evicted(monkeypatch) -> None:
    seen = {}

    def capture_connector(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["password"] = body.get("password")
        return _ok_connector(request)

    password_store.put("job1", "utt1", "row-secret")
    process_row(
        _job(expects_password=True), _utterance(),
        conn_client=_client(capture_connector), eval_client=_client(_ok_evaluator),
    )
    assert seen["password"] == "row-secret"  # forwarded to the connector body
    assert password_store.get("job1", "utt1") is None  # evicted (SC-008)


def test_password_omitted_when_not_expected() -> None:
    seen = {}

    def capture_connector(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _ok_connector(request)

    process_row(
        _job(expects_password=False), _utterance(),
        conn_client=_client(capture_connector), eval_client=_client(_ok_evaluator),
    )
    assert "password" not in seen["body"]


# --------------------------------------------------------------------------- US2
def test_connector_response_failure() -> None:
    data = process_row(
        _job(), _utterance(),
        conn_client=_client(lambda r: httpx.Response(500, text="boom")),
        eval_client=_client(_ok_evaluator),
    )
    assert data["error_status"] == "failed"
    assert data["error_stage"] == "connector_response"
    assert data.get("normalized_contract") is None
    assert data["evaluation_agent_id"] == "mock-evaluator"  # snapshot, never null


def test_connector_normalization_failure() -> None:
    data = process_row(
        _job(), _utterance(),
        conn_client=_client(lambda r: httpx.Response(200, json={"not": "a contract"})),
        eval_client=_client(_ok_evaluator),
    )
    assert data["error_stage"] == "connector_normalization"


def test_connector_transport_failure() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    data = process_row(
        _job(), _utterance(),
        conn_client=_client(refuse), eval_client=_client(_ok_evaluator),
    )
    assert data["error_stage"] == "connector_transport"


def test_evaluator_result_failure() -> None:
    data = process_row(
        _job(), _utterance(),
        conn_client=_client(_ok_connector),
        eval_client=_client(lambda r: httpx.Response(200, json={"verdict": "??"})),
    )
    assert data["error_status"] == "failed"
    assert data["error_stage"] == "evaluator_result"
    # connector stage succeeded → contract retained
    assert data["normalized_contract"] is not None
    assert data["raw_chatbot_response"] == {"echo": "hello"}


def test_evaluator_response_failure() -> None:
    data = process_row(
        _job(), _utterance(),
        conn_client=_client(_ok_connector),
        eval_client=_client(lambda r: httpx.Response(503, text="down")),
    )
    assert data["error_stage"] == "evaluator_response"


# ---------------------------------------------------------------------- tokens
def test_token_counts_both_present() -> None:
    def conn_with_tokens(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        contract = conn_mock.build_contract(body["testId"], body["utteranceText"])
        contract["tokenUsage"] = {"promptTokens": 100, "completionTokens": 50, "totalTokens": 150}
        return httpx.Response(200, json=contract)

    def ev_with_tokens(request: httpx.Request) -> httpx.Response:
        contract = json.loads(request.content)
        result = ev_mock.build_result(contract["utteranceId"], DIMS)
        result["tokenUsage"] = {"promptTokens": 200, "completionTokens": 75, "totalTokens": 275}
        return httpx.Response(200, json=result)

    data = process_row(
        _job(), _utterance(),
        conn_client=_client(conn_with_tokens), eval_client=_client(ev_with_tokens),
    )
    assert data["connector_token_count"] == 150
    assert data["evaluator_token_count"] == 275
    assert data["total_token_count"] == 425


def test_token_counts_absent() -> None:
    data = process_row(
        _job(), _utterance(),
        conn_client=_client(_ok_connector), eval_client=_client(_ok_evaluator),
    )
    assert data["connector_token_count"] is None
    assert data["evaluator_token_count"] is None
    assert data["total_token_count"] is None


def test_token_counts_connector_only_when_evaluator_fails() -> None:
    def conn_with_tokens(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        contract = conn_mock.build_contract(body["testId"], body["utteranceText"])
        contract["tokenUsage"] = {"totalTokens": 120}
        return httpx.Response(200, json=contract)

    data = process_row(
        _job(), _utterance(),
        conn_client=_client(conn_with_tokens),
        eval_client=_client(lambda r: httpx.Response(503, text="down")),
    )
    assert data["error_stage"] == "evaluator_response"
    assert data["connector_token_count"] == 120
    assert data.get("evaluator_token_count") is None
    assert data["total_token_count"] == 120
