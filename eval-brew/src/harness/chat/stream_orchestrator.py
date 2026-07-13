"""StreamOrchestrator — async connector→evaluator pipeline for one turn (017 US3).

Runs as a BackgroundTask. Consumes the connector's SSE stream, validates the
contract, invokes the evaluator, relays events to the browser event bus, and
batch-writes the completed result on success or records the failure on error.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from harness.chat.event_bus import TurnEventBus, remove_bus
from harness.persistence.encryption import decrypt_credential
from harness.persistence.engine import get_session
from harness.persistence.models.chat_session import ChatSession  # needed for DB fetch
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.remote.auth import build_auth_headers
from harness.remote.auth import decrypt_descriptor as decrypt_auth_descriptor
from harness.remote.oauth import TokenFetchError, resolve_auth_descriptor

log = logging.getLogger(__name__)

_STALL_TIMEOUT_SECONDS = 30


async def run_turn(
    turn_id: str,
    session_id: str,
    user_message: str,
    bus: TurnEventBus,
) -> None:
    """Async pipeline: connector stream → contract validation → evaluator stream.

    All DB reads and writes happen via fresh get_session() contexts so this
    coroutine is fully decoupled from the per-request session.
    """
    assembled_tokens: list[str] = []
    evaluation_events: list[dict] = []
    error_stage: str | None = None
    error_msg: str | None = None
    contract: dict | None = None
    final_result: dict | None = None

    # Fetch session snapshot from DB using orchestrator's own session so that
    # no detached-instance dependency exists on the caller's request session.
    with get_session() as _init_db:
        chat_session = _init_db.get(ChatSession, session_id)
        if chat_session is None:
            log.error(
                "run_turn: ChatSession %s not found; aborting turn %s", session_id, turn_id
            )
            await bus.mark_complete()
            remove_bus(turn_id)
            return
        test_id = decrypt_credential(chat_session.test_id_enc)
        password = decrypt_credential(chat_session.test_password_enc)
        connector_url = chat_session.connector_endpoint_url
        connector_timeout = chat_session.connector_timeout_seconds or 30
        evaluator_url = chat_session.evaluator_endpoint_url
        evaluator_timeout = chat_session.evaluator_timeout_seconds or 60
        connector_auth_descriptor = chat_session.connector_auth_descriptor
        evaluator_auth_descriptor = chat_session.evaluator_auth_descriptor

    try:
        connector_headers = await _build_auth_headers(
            connector_auth_descriptor, connector_timeout, "connector_auth"
        )

        # --- Phase 1: connector stream ---
        connector_body = {
            "auth": {"test_id": test_id, "password": password},
            "message": user_message,
        }
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream(
                    "POST", connector_url, json=connector_body, headers=connector_headers
                ) as response:
                    response.raise_for_status()
                    async for event_name, data_str in _iter_sse_events(response, connector_timeout):
                        if event_name == "token":
                            try:
                                payload = json.loads(data_str)
                                content = payload.get("content", "")
                                assembled_tokens.append(content)
                                await bus.publish(
                                    {"event": "connector_token", "data": {"content": content}}
                                )
                            except (json.JSONDecodeError, KeyError):
                                pass
                        elif event_name == "contract":
                            try:
                                contract = json.loads(data_str)
                            except json.JSONDecodeError as exc:
                                raise _StageError(
                                    "connector_normalization",
                                    f"Contract JSON decode error: {exc}",
                                ) from exc
                            break
            except _StageError:
                raise
            except httpx.HTTPStatusError as exc:
                raise _StageError(
                    "connector_stream",
                    f"Connector returned HTTP {exc.response.status_code}",
                ) from exc
            except (httpx.ConnectError, httpx.ReadTimeout, asyncio.TimeoutError) as exc:
                raise _StageError("connector_stream", f"Connector connection error: {exc}") from exc

        if contract is None:
            raise _StageError(
                "connector_stream", "Connector stream ended without a 'contract' event"
            )

        # --- Phase 2: contract validation ---
        try:
            _validate_contract(contract)
        except ValueError as exc:
            raise _StageError("connector_normalization", str(exc)) from exc

        # Signal browser that connector phase is done
        await bus.publish({"event": "evaluating", "data": {}})

        evaluator_headers = await _build_auth_headers(
            evaluator_auth_descriptor, evaluator_timeout, "evaluator_auth"
        )

        # --- Phase 3: evaluator stream ---
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                async with client.stream(
                    "POST", evaluator_url, json=contract, headers=evaluator_headers
                ) as response:
                    response.raise_for_status()
                    async for event_name, data_str in _iter_sse_events(response, evaluator_timeout):
                        if not event_name:
                            continue
                        try:
                            payload = json.loads(data_str)
                        except json.JSONDecodeError:
                            payload = {"raw": data_str}

                        evaluation_events.append(
                            {"event_type": event_name, "payload": payload}
                        )
                        await bus.publish(
                            {
                                "event": "evaluator_event",
                                "data": {"event_type": event_name, "payload": payload},
                            }
                        )
                        if event_name == "final":
                            final_result = payload
            except _StageError:
                raise
            except httpx.HTTPStatusError as exc:
                raise _StageError(
                    "evaluator_stream",
                    f"Evaluator returned HTTP {exc.response.status_code}",
                ) from exc
            except (httpx.ConnectError, httpx.ReadTimeout, asyncio.TimeoutError) as exc:
                raise _StageError("evaluator_stream", f"Evaluator connection error: {exc}") from exc

        if final_result is None:
            raise _StageError(
                "evaluator_stream", "Evaluator stream ended without a 'final' event"
            )

    except _StageError as exc:
        error_stage = exc.stage
        error_msg = exc.detail
    except Exception as exc:
        error_stage = "connector_stream"
        error_msg = f"Unexpected error: {exc}"
        log.exception("Unhandled error in StreamOrchestrator for turn %s", turn_id)

    assembled_response = "".join(assembled_tokens)

    # --- Persist result ---
    # mark_complete() is in a finally block so the browser SSE stream always
    # terminates even if the DB write itself fails (e.g. disk full, lock timeout).
    try:
        with get_session() as db_session:
            repo = ChatSessionRepository(db_session)
            if error_stage:
                repo.fail_turn(
                    turn_id,
                    error_stage=error_stage,
                    error_details=error_msg or "",
                    assembled_response=assembled_response or None,
                    evaluation_events=evaluation_events,
                )
                await bus.publish(
                    {
                        "event": "turn_failed",
                        "data": {
                            "turn_id": turn_id,
                            "error_stage": error_stage,
                            "error_details": error_msg or "",
                        },
                    }
                )
            else:
                repo.complete_turn(
                    turn_id,
                    assembled_response=assembled_response,
                    normalized_contract=contract,
                    final_evaluation_result=final_result,
                    evaluation_events=evaluation_events,
                )
                await bus.publish(
                    {
                        "event": "turn_complete",
                        "data": {
                            "turn_id": turn_id,
                            "assembled_response": assembled_response,
                        },
                    }
                )
    except Exception:
        log.exception("Failed to persist turn result for turn %s", turn_id)
    finally:
        await bus.mark_complete()
        remove_bus(turn_id)


# ---------------------------------------------------------------------------
# Helpers

async def _build_auth_headers(
    descriptor: dict | None, timeout: int, stage: str
) -> dict[str, str]:
    """Decrypt a snapshotted auth descriptor and return request headers.

    client-credentials token fetches are run in a thread so the async event
    loop is not blocked by sync httpx I/O.  Raises _StageError on any failure.
    """
    if not descriptor or descriptor.get("mode") == "none":
        return {}
    try:
        decrypted = decrypt_auth_descriptor(descriptor)
    except Exception as exc:
        raise _StageError(stage, f"Credential decryption failed: {exc}") from exc

    if decrypted.get("mode") == "client-credentials":
        try:
            resolved = await asyncio.to_thread(
                resolve_auth_descriptor, decrypted, timeout=timeout
            )
        except TokenFetchError as exc:
            raise _StageError(stage, f"Token fetch failed: {exc}") from exc
    else:
        resolved = decrypted

    try:
        return build_auth_headers(resolved)
    except ValueError as exc:
        raise _StageError(stage, f"Auth header build failed: {exc}") from exc


class _StageError(Exception):
    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(f"[{stage}] {detail}")


def _validate_contract(contract: dict) -> None:
    """Minimal structural check: require core contract fields."""
    if not isinstance(contract, dict):
        raise ValueError("Contract must be a JSON object")
    for field in ("utteranceId", "utteranceText", "chatbotResponse"):
        if field not in contract:
            raise ValueError(f"Contract missing required field '{field}'")


async def _aiter_with_timeout(ait, timeout_seconds: float):
    """Wrap an async iterable so each item fetch raises asyncio.TimeoutError on stall."""
    it = ait.__aiter__()
    while True:
        try:
            chunk = await asyncio.wait_for(it.__anext__(), timeout=timeout_seconds)
        except StopAsyncIteration:
            return
        yield chunk


async def _iter_sse_events(response: httpx.Response, timeout_seconds: float):
    """Yield (event_type, data_json) tuples from an SSE stream.

    Accumulates lines until a blank line terminates an event block.
    Ignores comment lines (starting with ':').
    Raises asyncio.TimeoutError if no chunk arrives within timeout_seconds.
    """
    event_name = ""
    data_lines: list[str] = []
    buffer = ""

    async for chunk in _aiter_with_timeout(response.aiter_text(), timeout_seconds):
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line.startswith(":"):
                continue
            if line == "":
                # Blank line = dispatch accumulated event
                if data_lines or event_name:
                    yield event_name, "\n".join(data_lines)
                event_name = ""
                data_lines = []
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
    # Flush any trailing event without trailing newline
    if data_lines or event_name:
        yield event_name, "\n".join(data_lines)
