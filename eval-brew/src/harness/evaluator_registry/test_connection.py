"""Non-blocking "Test connection" for the evaluator registry UI (FR-026-030).

POSTs a sample Standard Evaluation Contract and validates the RESPONSE as an
EvaluationResult (008). Reuses 008's validator + annotation helper, remote.auth,
and 007's mock contract builder. Never persists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from harness.connector.mock import build_contract
from harness.evaluator import compute_harness_annotations, validate_evaluation_result
from harness.remote.auth import build_auth_headers
from harness.remote.oauth import TokenFetchError, resolve_auth_descriptor

_TRUNCATE = 500
_TEST_UTTERANCE_ID = "test-utt"


@dataclass(frozen=True)
class TestConnectionResult:
    ok: bool
    # valid|invalid_result|http_error|unreachable|timeout|auth_config_error|auth_token_failed
    category: str
    status_code: int | None = None
    detail: str = ""
    warning: str | None = None


def run_test_connection(
    endpoint_url: str,
    decrypted_descriptor: dict,
    timeout_seconds: int,
    declared_dimensions: list[str],
    supports_sse: bool = False,
    *,
    client: httpx.Client | None = None,
) -> TestConnectionResult:
    """Send a sample contract; validate the response as an EvaluationResult (non-persisted)."""
    contract = build_contract("test-connection", "ping")
    contract["utteranceId"] = _TEST_UTTERANCE_ID  # FR-027: fixed sample

    if supports_sse:
        return _run_test_connection_sse(
            endpoint_url, decrypted_descriptor, timeout_seconds, declared_dimensions,
            contract, client=client,
        )

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=httpx.Timeout(timeout_seconds))
    try:
        # Resolve client-credentials to a bearer token (fetched via `client`) before
        # building headers; other modes pass through unchanged.
        try:
            descriptor = resolve_auth_descriptor(
                decrypted_descriptor, client=client, timeout=timeout_seconds, use_cache=False
            )
        except TokenFetchError as exc:
            return TestConnectionResult(False, "auth_token_failed", detail=str(exc))
        try:
            headers = {"Content-Type": "application/json", **build_auth_headers(descriptor)}
        except ValueError as exc:
            return TestConnectionResult(False, "auth_config_error", detail=str(exc))

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


def _run_test_connection_sse(
    endpoint_url: str,
    decrypted_descriptor: dict,
    timeout_seconds: int,
    declared_dimensions: list[str],
    contract: dict,
    *,
    client: httpx.Client | None = None,
) -> TestConnectionResult:
    """SSE-mode test: stream the response and validate the 'final' event payload."""
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=httpx.Timeout(timeout_seconds))
    try:
        try:
            descriptor = resolve_auth_descriptor(
                decrypted_descriptor, client=client, timeout=timeout_seconds, use_cache=False
            )
        except TokenFetchError as exc:
            return TestConnectionResult(False, "auth_token_failed", detail=str(exc))
        try:
            headers = {"Content-Type": "application/json", **build_auth_headers(descriptor)}
        except ValueError as exc:
            return TestConnectionResult(False, "auth_config_error", detail=str(exc))

        try:
            with client.stream("POST", endpoint_url, json=contract, headers=headers) as resp:
                if not 200 <= resp.status_code < 300:
                    body_snippet = resp.read().decode(errors="replace")[:_TRUNCATE]
                    return TestConnectionResult(
                        False, "http_error", status_code=resp.status_code, detail=body_snippet
                    )
                final_payload = _extract_final_from_sse(resp)
        except httpx.TimeoutException:
            return TestConnectionResult(
                False, "timeout", detail=f"timeout exceeded ({timeout_seconds}s)"
            )
        except httpx.HTTPError as exc:
            return TestConnectionResult(False, "unreachable", detail=f"endpoint unreachable: {exc}")

        if final_payload is None:
            return TestConnectionResult(
                False, "invalid_result", detail="SSE stream ended without a 'final' event"
            )

        problems = validate_evaluation_result(
            final_payload, expected_utterance_id=_TEST_UTTERANCE_ID
        )
        if problems:
            return TestConnectionResult(
                False, "invalid_result", status_code=200, detail="; ".join(problems[:3])
            )

        annotations = compute_harness_annotations(
            final_payload.get("evaluationScores", []), declared_dimensions
        )
        warning = None
        if annotations["unexpected_score_dimensions"]:
            warning = "endpoint emitted dimensions not in your declared list: " + ", ".join(
                annotations["unexpected_score_dimensions"]
            )
        return TestConnectionResult(
            True,
            "valid",
            status_code=200,
            detail="Endpoint returned a valid EvaluationResult via SSE stream.",
            warning=warning,
        )
    finally:
        if owns_client:
            client.close()


def _extract_final_from_sse(response: httpx.Response) -> dict | None:
    """Parse an SSE stream and return the payload of the first 'final' event, or None."""
    event_name = ""
    data_lines: list[str] = []
    buffer = ""

    for chunk in response.iter_text():
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line.startswith(":"):
                continue
            if line == "":
                if event_name == "final" and data_lines:
                    try:
                        return json.loads("\n".join(data_lines))
                    except json.JSONDecodeError:
                        return None
                event_name = ""
                data_lines = []
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())

    # Flush trailing event without final blank line
    if event_name == "final" and data_lines:
        try:
            return json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            return None
    return None
