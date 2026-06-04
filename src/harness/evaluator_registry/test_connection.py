"""Non-blocking "Test connection" for the evaluator registry UI (FR-026-030).

POSTs a sample Standard Evaluation Contract and validates the RESPONSE as an
EvaluationResult (008). Reuses 008's validator + annotation helper, remote.auth,
and 007's mock contract builder. Never persists.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from harness.connector.mock import build_contract
from harness.evaluator import compute_harness_annotations, validate_evaluation_result
from harness.remote.auth import build_auth_headers

_TRUNCATE = 500
_TEST_UTTERANCE_ID = "test-utt"


@dataclass(frozen=True)
class TestConnectionResult:
    ok: bool
    category: str  # valid|invalid_result|http_error|unreachable|timeout|auth_decrypt_failed
    status_code: int | None = None
    detail: str = ""
    warning: str | None = None


def run_test_connection(
    endpoint_url: str,
    decrypted_descriptor: dict,
    timeout_seconds: int,
    declared_dimensions: list[str],
    *,
    client: httpx.Client | None = None,
) -> TestConnectionResult:
    """Send a sample contract; validate the response as an EvaluationResult (non-persisted)."""
    contract = build_contract("test-connection", "ping")
    contract["utteranceId"] = _TEST_UTTERANCE_ID  # FR-027: fixed sample

    try:
        headers = {"Content-Type": "application/json", **build_auth_headers(decrypted_descriptor)}
    except ValueError as exc:
        return TestConnectionResult(False, "auth_decrypt_failed", detail=str(exc))

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=httpx.Timeout(timeout_seconds))
    try:
        try:
            response = client.post(endpoint_url, json=contract, headers=headers)
        except httpx.TimeoutException:
            return TestConnectionResult(
                False, "timeout", detail=f"timeout exceeded ({timeout_seconds}s)"
            )
        except httpx.HTTPError as exc:
            return TestConnectionResult(False, "unreachable", detail=f"endpoint unreachable: {exc}")

        if not 200 <= response.status_code < 300:
            return TestConnectionResult(
                False,
                "http_error",
                status_code=response.status_code,
                detail=response.text[:_TRUNCATE],
            )

        try:
            body = response.json()
        except ValueError:
            return TestConnectionResult(
                False,
                "invalid_result",
                status_code=response.status_code,
                detail="response is not valid JSON",
            )

        problems = validate_evaluation_result(body, expected_utterance_id=_TEST_UTTERANCE_ID)
        if problems:
            return TestConnectionResult(
                False,
                "invalid_result",
                status_code=response.status_code,
                detail="; ".join(problems[:3]),
            )

        annotations = compute_harness_annotations(
            body.get("evaluationScores", []), declared_dimensions
        )
        warning = None
        if annotations["unexpected_score_dimensions"]:
            warning = "endpoint emitted dimensions not in your declared list: " + ", ".join(
                annotations["unexpected_score_dimensions"]
            )
        return TestConnectionResult(
            True,
            "valid",
            status_code=response.status_code,
            detail="Endpoint returned a valid EvaluationResult.",
            warning=warning,
        )
    finally:
        if owns_client:
            client.close()
