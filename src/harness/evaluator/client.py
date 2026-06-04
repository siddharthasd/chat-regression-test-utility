"""The per-row evaluator HTTP client (FR-001..006a).

`dispatch_evaluation` POSTs the contract instance to the evaluator, validates the
returned EvaluationResult, derives harness annotations, never retries, never
caches (FR-018). Consumed by the orchestrator (012).
"""

from __future__ import annotations

import httpx

from harness.evaluator.result import EvaluatorResult, EvaluatorSnapshot
from harness.evaluator.validation import compute_harness_annotations, validate_evaluation_result
from harness.persistence.exceptions import HarnessKeyMismatchError
from harness.remote.auth import build_auth_headers, decrypt_descriptor

_BODY_TRUNCATE = 2000


def dispatch_evaluation(
    snapshot: EvaluatorSnapshot,
    contract: dict,
    *,
    client: httpx.Client | None = None,
) -> EvaluatorResult:
    """POST the contract to the evaluator; validate the result or categorize failure.

    No caching/dedup — every call issues a fresh request (FR-018). `client` is
    injectable for MockTransport tests.
    """
    try:
        descriptor = decrypt_descriptor(snapshot.auth_descriptor)
    except HarnessKeyMismatchError:
        return EvaluatorResult(
            ok=False,
            error_stage="evaluator_auth",
            error_details="machine-local key missing or wrong",
        )

    headers = {"Content-Type": "application/json", **build_auth_headers(descriptor)}
    expected_uid = contract.get("utteranceId") if isinstance(contract, dict) else None

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=httpx.Timeout(snapshot.timeout_seconds))
    try:
        try:
            response = client.post(snapshot.endpoint_url, json=contract, headers=headers)
        except httpx.TimeoutException:
            return EvaluatorResult(
                ok=False,
                error_stage="evaluator_transport",
                error_details=f"timeout exceeded ({snapshot.timeout_seconds}s)",
            )
        except httpx.HTTPError as exc:
            return EvaluatorResult(
                ok=False,
                error_stage="evaluator_transport",
                error_details=f"transport error: {exc}",
            )

        if not 200 <= response.status_code < 300:
            return EvaluatorResult(
                ok=False,
                error_stage="evaluator_response",
                error_details=response.text[:_BODY_TRUNCATE],
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError:
            return EvaluatorResult(
                ok=False,
                error_stage="evaluator_result",
                error_details="response body is not valid JSON: " + response.text[:_BODY_TRUNCATE],
                status_code=response.status_code,
            )

        problems = validate_evaluation_result(body, expected_utterance_id=expected_uid)
        if problems:
            return EvaluatorResult(
                ok=False,
                error_stage="evaluator_result",
                error_details="; ".join(problems[:5]),
                status_code=response.status_code,
            )

        annotations = compute_harness_annotations(
            body.get("evaluationScores", []), snapshot.declared_scoring_dimensions
        )
        return EvaluatorResult(
            ok=True,
            evaluation_result=body,
            harness_annotations=annotations,
            status_code=response.status_code,
        )
    finally:
        if owns_client:
            client.close()
