"""run_test_connection categorized-outcome tests (FR-022/023, SC-008/009)."""

from __future__ import annotations

import json

import httpx

from harness.connector import mock
from harness.connector_registry import run_test_connection


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _valid(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=mock.build_contract("test-connection", "ping"))


def test_valid_contract() -> None:
    r = run_test_connection("http://c/", {"mode": "none"}, 10, False, client=_client(_valid))
    assert r.ok is True
    assert r.category == "valid"


def test_http_error() -> None:
    client = _client(lambda req: httpx.Response(500, text="boom"))
    r = run_test_connection("http://c/", {"mode": "none"}, 10, False, client=client)
    assert r.category == "http_error"
    assert r.status_code == 500


def test_invalid_contract() -> None:
    client = _client(lambda req: httpx.Response(200, json={"x": 1}))
    r = run_test_connection("http://c/", {"mode": "none"}, 10, False, client=client)
    assert r.category == "invalid_contract"


def test_unreachable() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    r = run_test_connection("http://c/", {"mode": "none"}, 10, False, client=_client(h))
    assert r.category == "unreachable"


def test_timeout() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("t", request=request)

    r = run_test_connection("http://c/", {"mode": "none"}, 10, False, client=_client(h))
    assert r.category == "timeout"


def test_password_included_when_expected() -> None:
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=mock.build_contract("test-connection", "ping"))

    run_test_connection("http://c/", {"mode": "none"}, 10, True, client=_client(h))
    assert captured["body"]["password"] == "test"
