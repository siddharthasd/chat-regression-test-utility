"""dispatch_utterance tests (US1 dispatch + errorStage; US3 credential paths).

Driven by httpx.MockTransport — no socket. Covers FR-002/003/004/006/015/016,
SC-006/008/009/010.
"""

from __future__ import annotations

import json

import httpx

from harness.connector import ConnectorSnapshot, UtteranceRow, dispatch_utterance, mock
from harness.persistence import encryption


def _snap(auth: dict | None = None, expects: bool = False, timeout: int = 10) -> ConnectorSnapshot:
    return ConnectorSnapshot(
        connector_id="mock",
        endpoint_url="http://conn.test/",
        auth_descriptor=auth or {"mode": "none"},
        timeout_seconds=timeout,
        expects_per_row_password=expects,
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=mock.build_contract("t1", "hi"))


# ------------------------------------------------------------------ US1
def test_success_returns_contract() -> None:
    r = dispatch_utterance(_snap(), UtteranceRow("t1", "hi"), client=_client(_ok))
    assert r.ok is True
    assert r.contract["connectorId"] == "mock"
    assert r.status_code == 200


def test_exactly_one_request_per_dispatch() -> None:
    calls: list[int] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=mock.build_contract("t", "h"))

    dispatch_utterance(_snap(), UtteranceRow("t", "h"), client=_client(h))
    assert len(calls) == 1  # SC-006: one request per row, no retry


def test_body_omits_password_when_not_expected() -> None:
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=mock.build_contract("t", "h"))

    dispatch_utterance(
        _snap(expects=False), UtteranceRow("t", "h", password="pw"), client=_client(h)
    )
    assert "password" not in captured["body"]
    assert captured["body"] == {"testId": "t", "utteranceText": "h"}


def test_body_includes_password_when_expected() -> None:
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=mock.build_contract("t", "h"))

    dispatch_utterance(
        _snap(expects=True), UtteranceRow("t", "h", password="pw"), client=_client(h)
    )
    assert captured["body"]["password"] == "pw"


# ------------------------------------------------------------------ US1 error mapping
def test_non_2xx_is_connector_response() -> None:
    r = dispatch_utterance(
        _snap(),
        UtteranceRow("t", "h"),
        client=_client(lambda req: httpx.Response(500, text="boom")),
    )
    assert r.error_stage == "connector_response"
    assert r.status_code == 500
    assert "boom" in r.error_details


def test_invalid_json_is_connector_normalization() -> None:
    r = dispatch_utterance(
        _snap(),
        UtteranceRow("t", "h"),
        client=_client(lambda req: httpx.Response(200, text="{not json")),
    )
    assert r.error_stage == "connector_normalization"


def test_nonconformant_body_is_connector_normalization() -> None:
    r = dispatch_utterance(
        _snap(),
        UtteranceRow("t", "h"),
        client=_client(lambda req: httpx.Response(200, json={"nope": 1})),
    )
    assert r.error_stage == "connector_normalization"


def test_timeout_is_connector_transport() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    r = dispatch_utterance(_snap(), UtteranceRow("t", "h"), client=_client(h))
    assert r.error_stage == "connector_transport"
    assert "timeout" in r.error_details.lower()


def test_connect_error_is_connector_transport() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    r = dispatch_utterance(_snap(), UtteranceRow("t", "h"), client=_client(h))
    assert r.error_stage == "connector_transport"


# ------------------------------------------------------------------ US3 credential paths
def test_auth_header_built_from_decrypted_bearer() -> None:
    ciphertext = encryption.encrypt_credential("SECRET-TOK")
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=mock.build_contract("t", "h"))

    dispatch_utterance(
        _snap(auth={"mode": "bearer", "credential": ciphertext}),
        UtteranceRow("t", "h"),
        client=_client(h),
    )
    assert captured["auth"] == "Bearer SECRET-TOK"


def test_decrypt_failure_is_connector_auth() -> None:
    r = dispatch_utterance(
        _snap(auth={"mode": "bearer", "credential": "not-valid-ciphertext"}),
        UtteranceRow("t", "h"),
        client=_client(_ok),
    )
    assert r.ok is False
    assert r.error_stage == "connector_auth"
    assert "machine-local key" in r.error_details


def test_no_plaintext_credential_in_result() -> None:
    ciphertext = encryption.encrypt_credential("DISTINCT-TOKEN-XYZ")
    r = dispatch_utterance(
        _snap(auth={"mode": "bearer", "credential": ciphertext}),
        UtteranceRow("t", "h"),
        client=_client(_ok),
    )
    assert "DISTINCT-TOKEN-XYZ" not in repr(r)  # plaintext never surfaces in the result
