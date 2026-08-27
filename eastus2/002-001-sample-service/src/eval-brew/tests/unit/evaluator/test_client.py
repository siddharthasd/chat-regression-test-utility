"""dispatch_evaluation tests (US1 + US3 annotation; US1 credential paths).

Driven by httpx.MockTransport. Covers FR-002/005b/006a/015/016/017, SC-006/007/008/009.
"""

from __future__ import annotations

import json

import httpx

from harness.evaluator import EvaluatorSnapshot, dispatch_evaluation, mock
from harness.persistence import encryption
from harness.remote import oauth

CONTRACT = {"utteranceId": "u-1", "utteranceText": "hi", "testId": "t1"}


def _snap(auth: dict | None = None, dims: tuple[str, ...] = ("relevance",), timeout: int = 10):
    return EvaluatorSnapshot(
        evaluation_agent_id="mock-evaluator",
        endpoint_url="http://eval.test/",
        auth_descriptor=auth or {"mode": "none"},
        timeout_seconds=timeout,
        declared_scoring_dimensions=list(dims),
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=mock.build_result("u-1", ["relevance"]))


# ------------------------------------------------------------------ US1 success
def test_success_returns_result_and_annotations() -> None:
    r = dispatch_evaluation(_snap(), CONTRACT, client=_client(_ok))
    assert r.ok is True
    assert r.evaluation_result["evaluationAgentId"] == "mock-evaluator"
    assert r.harness_annotations == {"unexpected_score_dimensions": []}


def test_body_is_contract_verbatim() -> None:
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=mock.build_result("u-1", ["relevance"]))

    dispatch_evaluation(_snap(), CONTRACT, client=_client(h))
    assert captured["body"] == CONTRACT
    assert "password" not in captured["body"]  # FR-017


def test_exactly_one_request() -> None:
    calls: list[int] = []

    def h(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=mock.build_result("u-1", ["relevance"]))

    dispatch_evaluation(_snap(), CONTRACT, client=_client(h))
    assert len(calls) == 1


def test_unexpected_dimension_annotated_not_rejected() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock.build_result("u-1", ["relevance", "SURPRISE"]))

    r = dispatch_evaluation(_snap(dims=("relevance",)), CONTRACT, client=_client(h))
    assert r.ok is True
    assert r.harness_annotations == {"unexpected_score_dimensions": ["SURPRISE"]}


# ------------------------------------------------------------------ error mapping
def test_non_2xx_is_evaluator_response() -> None:
    r = dispatch_evaluation(
        _snap(), CONTRACT, client=_client(lambda req: httpx.Response(500, text="boom"))
    )
    assert r.error_stage == "evaluator_response"
    assert r.status_code == 500


def test_bad_result_is_evaluator_result() -> None:
    r = dispatch_evaluation(
        _snap(), CONTRACT, client=_client(lambda req: httpx.Response(200, json={"verdict": "x"}))
    )
    assert r.error_stage == "evaluator_result"


def test_invalid_json_is_evaluator_result() -> None:
    r = dispatch_evaluation(
        _snap(), CONTRACT, client=_client(lambda req: httpx.Response(200, text="{bad"))
    )
    assert r.error_stage == "evaluator_result"


def test_timeout_is_evaluator_transport() -> None:
    def h(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    r = dispatch_evaluation(_snap(), CONTRACT, client=_client(h))
    assert r.error_stage == "evaluator_transport"


# ------------------------------------------------------------------ credential paths
def test_auth_header_built_from_decrypted_bearer() -> None:
    ciphertext = encryption.encrypt_credential("EVAL-TOK")
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=mock.build_result("u-1", ["relevance"]))

    dispatch_evaluation(
        _snap(auth={"mode": "bearer", "credential": ciphertext}), CONTRACT, client=_client(h)
    )
    assert captured["auth"] == "Bearer EVAL-TOK"


# ------------------------------------------------------------------ client-credentials
def _cc_auth() -> dict:
    return {
        "mode": "client-credentials",
        "tokenUrl": "http://idp.test/token",
        "clientId": "cid",
        "clientSecret": encryption.encrypt_credential("SHHH"),
    }


def test_client_credentials_fetches_token_then_sends_bearer() -> None:
    oauth.reset_token_cache()
    captured: dict = {}

    def h(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://idp.test/token":
            assert b"client_secret=SHHH" in request.content  # decrypted secret used
            return httpx.Response(200, json={"access_token": "AT", "expires_in": 3600})
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=mock.build_result("u-1", ["relevance"]))

    r = dispatch_evaluation(_snap(auth=_cc_auth()), CONTRACT, client=_client(h))
    assert r.ok is True
    assert captured["auth"] == "Bearer AT"


def test_client_credentials_token_failure_is_evaluator_auth() -> None:
    oauth.reset_token_cache()

    def h(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://idp.test/token":
            return httpx.Response(401, text="bad client")
        return httpx.Response(200, json=mock.build_result("u-1", ["relevance"]))

    r = dispatch_evaluation(_snap(auth=_cc_auth()), CONTRACT, client=_client(h))
    assert r.ok is False
    assert r.error_stage == "evaluator_auth"
    assert "token fetch failed" in r.error_details
