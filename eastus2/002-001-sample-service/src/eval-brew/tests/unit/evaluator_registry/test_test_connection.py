"""run_test_connection (evaluator) categorized-outcome + dimension-warning tests (FR-028/029)."""

from __future__ import annotations

import httpx

from harness.evaluator import mock as ev_mock
from harness.evaluator_registry import run_test_connection


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _valid(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=ev_mock.build_result("test-utt", ["relevance"]))


def test_valid_evaluation_result() -> None:
    r = run_test_connection(
        "http://e/", {"mode": "none"}, 10, ["relevance"], client=_client(_valid)
    )
    assert r.ok is True
    assert r.category == "valid"
    assert r.warning is None


def test_invalid_result() -> None:
    client = _client(lambda req: httpx.Response(200, json={"verdict": "maybe"}))
    r = run_test_connection("http://e/", {"mode": "none"}, 10, [], client=client)
    assert r.category == "invalid_result"


def test_http_error() -> None:
    client = _client(lambda req: httpx.Response(500, text="boom"))
    r = run_test_connection("http://e/", {"mode": "none"}, 10, [], client=client)
    assert r.category == "http_error"
    assert r.status_code == 500


def test_unreachable() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    r = run_test_connection("http://e/", {"mode": "none"}, 10, [], client=_client(h))
    assert r.category == "unreachable"


def test_timeout() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("t", request=request)

    r = run_test_connection("http://e/", {"mode": "none"}, 10, [], client=_client(h))
    assert r.category == "timeout"


def test_dimension_divergence_soft_warning() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ev_mock.build_result("test-utt", ["relevance", "SURPRISE"]))

    r = run_test_connection("http://e/", {"mode": "none"}, 10, ["relevance"], client=_client(h))
    assert r.ok is True
    assert r.warning is not None
    assert "SURPRISE" in r.warning
