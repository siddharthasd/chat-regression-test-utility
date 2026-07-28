"""Non-blocking "Test connection" for the registry UI (FR-021-025).

Fires one sample request at a connector endpoint and categorizes the outcome.
Reuses harness.remote.auth (auth header) + harness.contract (2xx validation).
Never persists anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from harness.contract import validate_contract
from harness.remote.auth import build_auth_headers
from harness.remote.oauth import TokenFetchError, resolve_auth_descriptor

_SAMPLE_BODY = {"testId": "test-connection", "utteranceText": "ping"}
_SSE_SAMPLE_BODY = {
    "auth": {"test_id": "test-connection", "password": ""},
    "message": "ping",
}
_TRUNCATE = 500


@dataclass(frozen=True)
class TestConnectionResult:
    ok: bool
    # valid|invalid_contract|http_error|unreachable|timeout|auth_config_error|auth_token_failed
    category: str
    status_code: int | None = None
    detail: str = ""


def run_test_connection(
    endpoint_url: str,
    decrypted_descriptor: dict,
    timeout_seconds: int,
    expects_per_row_password: bool,
    supports_sse: bool = False,
    *,
    client: httpx.Client | None = None,
) -> TestConnectionResult:
    """Send the fixed sample request; return a categorized, non-persisted result."""
    if supports_sse:
        return _run_test_connection_sse(
            endpoint_url, decrypted_descriptor, timeout_seconds,
            expects_per_row_password=expects_per_row_password, client=client,
        )

    body = dict(_SAMPLE_BODY)
    if expects_per_row_password:
        body["password"] = "test"

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
            response = client.post(endpoint_url, json=body, headers=headers)
        except httpx.TimeoutException:
            return TestConnectionResult(
                False, "timeout", detail=f"timeout exceeded ({timeout_seconds}s)"
            )
        except httpx.HTTPError as exc:  # connect / DNS / TLS / protocol
            return TestConnectionResult(False, "unreachable", detail=f"endpoint unreachable: {exc}")

        if not 200 <= response.status_code < 300:
            return TestConnectionResult(
                False,
                "http_error",
                status_code=response.status_code,
                detail=response.text[:_TRUNCATE],
            )

        try:
            instance = response.json()
        except ValueError:
            return TestConnectionResult(
                False,
                "invalid_contract",
                status_code=response.status_code,
                detail="response is not valid JSON",
            )

        result = validate_contract(instance)
        if result.valid:
            return TestConnectionResult(
                True,
                "valid",
                status_code=response.status_code,
                detail="Endpoint returned a valid Standard Evaluation Contract instance.",
            )
        summary = "; ".join(f"{v.field_path}: {v.kind}" for v in result.violations[:3])
        return TestConnectionResult(
            False,
            "invalid_contract",
            status_code=response.status_code,
            detail=f"response is not a valid contract: {summary}",
        )
    finally:
        if owns_client:
            client.close()


def _run_test_connection_sse(
    endpoint_url: str,
    decrypted_descriptor: dict,
    timeout_seconds: int,
    *,
    expects_per_row_password: bool = False,
    client: httpx.Client | None = None,
) -> TestConnectionResult:
    """SSE-mode test: stream the response and validate the 'contract' event payload."""
    body = dict(_SSE_SAMPLE_BODY)
    body["auth"] = dict(body["auth"])
    if expects_per_row_password:
        body["auth"]["password"] = "test"

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
            with client.stream("POST", endpoint_url, json=body, headers=headers) as resp:
                if not 200 <= resp.status_code < 300:
                    body_snippet = resp.read().decode(errors="replace")[:_TRUNCATE]
                    return TestConnectionResult(
                        False, "http_error", status_code=resp.status_code, detail=body_snippet
                    )

                contract = _extract_contract_from_sse(resp)
        except httpx.TimeoutException:
            return TestConnectionResult(
                False, "timeout", detail=f"timeout exceeded ({timeout_seconds}s)"
            )
        except httpx.HTTPError as exc:
            return TestConnectionResult(False, "unreachable", detail=f"endpoint unreachable: {exc}")

        if contract is None:
            return TestConnectionResult(
                False, "invalid_contract", detail="SSE stream ended without a 'contract' event"
            )

        result = validate_contract(contract)
        if result.valid:
            return TestConnectionResult(
                True,
                "valid",
                status_code=200,
                detail="Endpoint returned a valid Standard Evaluation Contract via SSE stream.",
            )
        summary = "; ".join(f"{v.field_path}: {v.kind}" for v in result.violations[:3])
        return TestConnectionResult(
            False,
            "invalid_contract",
            status_code=200,
            detail=f"contract event is not a valid contract: {summary}",
        )
    finally:
        if owns_client:
            client.close()


def _extract_contract_from_sse(response: httpx.Response) -> dict | None:
    """Parse an SSE stream and return the payload of the first 'contract' event, or None."""
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
                if event_name == "contract" and data_lines:
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
    if event_name == "contract" and data_lines:
        try:
            return json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            return None
    return None
