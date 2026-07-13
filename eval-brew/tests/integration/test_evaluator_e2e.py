"""End-to-end evaluator tests over a real mock server (US1/US2/US4).

Covers SC-001/002/005/006/007/008/009.
"""

from __future__ import annotations

import contextlib
import threading

from harness.evaluator import (
    EvaluatorRegistryReader,
    EvaluatorSnapshot,
    dispatch_evaluation,
    mock,
)
from harness.persistence.repositories import EvaluationAgentRegistrationRepository

_CONTRACT = {
    "utteranceId": "u-1",
    "utteranceText": "hi",
    "testId": "t1",
    "conversationContext": None,
    "connectorId": "c",
    "contractVersion": "1",
    "timestamp": "2026-06-04T12:00:00Z",
    "chatbotResponse": {"rawPayload": {}, "normalizedText": "x", "agentChain": [], "metadata": {}},
}


@contextlib.contextmanager
def running(mode: str = "ok", dimensions=("relevance",), slow_seconds: int = 5):
    server = mock.make_server(
        port=0, mode=mode, dimensions=list(dimensions), slow_seconds=slow_seconds
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def _snap(url: str, timeout: int = 10) -> EvaluatorSnapshot:
    return EvaluatorSnapshot("mock-evaluator", url, {"mode": "none"}, timeout, ["relevance"])


def test_end_to_end_result_valid() -> None:
    with running() as url:
        result = dispatch_evaluation(_snap(url), _CONTRACT)
    assert result.ok  # SC-001
    assert result.evaluation_result["evaluationVerdict"] in {"pass", "fail", "warn"}


def test_register_and_run_no_core_change(db_session) -> None:
    with running() as url:
        reg = EvaluationAgentRegistrationRepository(db_session).create(
            {
                "display_name": "Mock Eval",
                "description": "mock",
                "endpoint_url": url,
                "auth_descriptor": {"mode": "none"},
                "declared_scoring_dimensions": ["relevance"],
            }
        )
        reader = EvaluatorRegistryReader(db_session)
        assert reg.evaluation_agent_id in {e.evaluation_agent_id for e in reader.list_active()}
        full = reader.get(reg.evaluation_agent_id)
        snap = EvaluatorSnapshot(
            full.evaluation_agent_id,
            full.endpoint_url,
            full.auth_descriptor,
            full.timeout_seconds,
            list(full.declared_scoring_dimensions),
        )
        result = dispatch_evaluation(snap, _CONTRACT)
    assert result.ok  # SC-002


def test_same_input_two_calls_differ() -> None:
    # SC-005/006: two POSTs, no caching, results may differ.
    with running() as url:
        snap = _snap(url)
        a = dispatch_evaluation(snap, _CONTRACT)
        b = dispatch_evaluation(snap, _CONTRACT)
    assert a.ok and b.ok
    differ = (
        a.evaluation_result["evaluationVerdict"] != b.evaluation_result["evaluationVerdict"]
        or [s["score"] for s in a.evaluation_result["evaluationScores"]]
        != [s["score"] for s in b.evaluation_result["evaluationScores"]]
    )
    assert differ


def test_non_2xx_is_evaluator_response() -> None:
    with running(mode="status500") as url:
        result = dispatch_evaluation(_snap(url), _CONTRACT)
    assert result.error_stage == "evaluator_response"  # SC-008


def test_malformed_is_evaluator_result() -> None:
    with running(mode="nonconformant") as url:
        result = dispatch_evaluation(_snap(url), _CONTRACT)
    assert result.error_stage == "evaluator_result"  # SC-007


def test_timeout_is_evaluator_transport() -> None:
    with running(mode="slow", slow_seconds=3) as url:
        result = dispatch_evaluation(_snap(url, timeout=1), _CONTRACT)
    assert result.error_stage == "evaluator_transport"  # SC-009
