"""The per-row connector HTTP client (FR-001..006).

`dispatch_utterance` issues one stateless POST, enforces the timeout, never
retries, and maps every failure onto the canonical connector error stages.
Consumed by the orchestrator (012); the per-job loop/serialization is 012's.
"""

from __future__ import annotations

import httpx

from harness.connector.result import ConnectorResult, ConnectorSnapshot, UtteranceRow
from harness.contract import validate_contract
from harness.persistence.exceptions import HarnessKeyMismatchError
from harness.remote.auth import build_auth_headers, decrypt_descriptor
from harness.remote.oauth import TokenFetchError, resolve_auth_descriptor

_BODY_TRUNCATE = 2000


def _build_body(snapshot: ConnectorSnapshot, row: UtteranceRow) -> dict:
    body = {"testId": row.test_id, "utteranceText": row.utterance_text}
    # password present iff the connector expects it; omitted entirely otherwise (FR-002).
    if snapshot.expects_per_row_password:
        body["password"] = row.password
    return body


def dispatch_utterance(
    snapshot: ConnectorSnapshot,
    row: UtteranceRow,
    *,
    client: httpx.Client | None = None,
) -> ConnectorResult:
    """Dispatch one utterance to a connector endpoint; return a validated contract
    or a categorized failure. `client` is injectable for MockTransport tests."""
    # 1. Decrypt credentials before sending; a key failure means no request goes out.
    try:
        descriptor = decrypt_descriptor(snapshot.auth_descriptor)
    except HarnessKeyMismatchError:
        return ConnectorResult(
            ok=False,
            error_stage="connector_auth",
            error_details="machine-local key missing or wrong",
        )

    body = _build_body(snapshot, row)

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=httpx.Timeout(snapshot.timeout_seconds))
    try:
        # 2. Resolve the descriptor (client-credentials fetches a token via `client`,
        #    reusing the per-row timeout); other modes pass through unchanged.
        try:
            descriptor = resolve_auth_descriptor(
                descriptor, client=client, timeout=snapshot.timeout_seconds
            )
        except TokenFetchError as exc:
            return ConnectorResult(
                ok=False,
                error_stage="connector_auth",
                error_details=f"token fetch failed: {exc}",
            )
        headers = {"Content-Type": "application/json", **build_auth_headers(descriptor)}

        try:
            response = client.post(snapshot.endpoint_url, json=body, headers=headers)
        except httpx.TimeoutException:
            return ConnectorResult(
                ok=False,
                error_stage="connector_transport",
                error_details=f"timeout exceeded ({snapshot.timeout_seconds}s)",
            )
        except httpx.HTTPError as exc:  # connect / DNS / TLS / protocol errors
            return ConnectorResult(
                ok=False,
                error_stage="connector_transport",
                error_details=f"transport error: {exc}",
            )

        if not 200 <= response.status_code < 300:
            return ConnectorResult(
                ok=False,
                error_stage="connector_response",
                error_details=response.text[:_BODY_TRUNCATE],
                status_code=response.status_code,
            )

        try:
            instance = response.json()
        except ValueError:
            return ConnectorResult(
                ok=False,
                error_stage="connector_normalization",
                error_details="response body is not valid JSON: "
                + response.text[:_BODY_TRUNCATE],
                status_code=response.status_code,
            )

        result = validate_contract(instance)
        if not result.valid:
            summary = "; ".join(
                f"{v.field_path}: {v.kind}" for v in result.violations[:5]
            )
            return ConnectorResult(
                ok=False,
                error_stage="connector_normalization",
                error_details=f"contract validation failed: {summary}",
                status_code=response.status_code,
            )

        return ConnectorResult(ok=True, contract=instance, status_code=response.status_code)
    finally:
        if owns_client:
            client.close()
