"""Per-row pipeline: one Utterance -> one EvaluationResult create-payload (012 FR-011).

`process_row` is the orchestrator's glue. It builds the client snapshots from the
Job's snapshotted config (FR-004), looks up + evicts the row password (FR-011
steps 1/3), delegates the two HTTP calls to `harness.connector.dispatch_utterance`
and `harness.evaluator.dispatch_evaluation` (which already validate, enforce
timeouts, map the 9-value error stages, and compute harness annotations), and maps
the outcome onto an `EvaluationResultCreateData` (data-model.md §5). It performs no
validation or retries of its own (FR-013) and never raises for a per-row failure —
a failure becomes a persisted `failed` row (FR-012).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from harness import password_store
from harness.connector import dispatch_utterance
from harness.connector.result import ConnectorSnapshot, UtteranceRow
from harness.evaluator import dispatch_evaluation
from harness.evaluator.result import EvaluatorSnapshot
from harness.persistence.repositories.types import EvaluationResultCreateData

if TYPE_CHECKING:
    from harness.persistence.models import Job, Utterance


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: object) -> datetime:
    """Parse the evaluator's emitted ISO timestamp; fall back to now (FR-011 step 8)."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return _utcnow()


def _connector_snapshot(job: Job) -> ConnectorSnapshot:
    return ConnectorSnapshot(
        connector_id=job.connector_id,
        endpoint_url=job.connector_endpoint_url,
        auth_descriptor=job.connector_auth_descriptor,
        timeout_seconds=job.connector_timeout_seconds,
        expects_per_row_password=job.connector_expects_per_row_password,
    )


def _evaluator_snapshot(job: Job) -> EvaluatorSnapshot:
    return EvaluatorSnapshot(
        evaluation_agent_id=job.evaluation_agent_id,
        endpoint_url=job.evaluator_endpoint_url,
        auth_descriptor=job.evaluator_auth_descriptor,
        timeout_seconds=job.evaluator_timeout_seconds,
        declared_scoring_dimensions=job.evaluator_declared_scoring_dimensions or [],
    )


def process_row(
    job: Job,
    utterance: Utterance,
    *,
    conn_client: httpx.Client | None = None,
    eval_client: httpx.Client | None = None,
) -> EvaluationResultCreateData:
    """Run one row's connector→evaluator pipeline; return its create-payload.

    `conn_client`/`eval_client` are injectable for MockTransport tests. The Job's
    `evaluation_agent_id` is always copied onto the row so the column is never null,
    even on a connector-stage failure (009 FR-003).
    """
    password = (
        password_store.get(job.job_id, utterance.utterance_id)
        if job.connector_expects_per_row_password
        else None
    )
    row = UtteranceRow(
        test_id=utterance.test_id,
        utterance_text=utterance.utterance_text,
        password=password,
    )
    conn = dispatch_utterance(_connector_snapshot(job), row, client=conn_client)
    # Per-row eviction: immediately after the connector call returns, regardless of
    # outcome (012 FR-011 step 3 / SC-008).
    password_store.evict(job.job_id, utterance.utterance_id)

    data: EvaluationResultCreateData = {
        "utterance_id": utterance.utterance_id,
        "test_id": utterance.test_id,
        "evaluation_agent_id": job.evaluation_agent_id,
        "evaluation_timestamp": _utcnow(),
    }

    if not conn.ok:
        data["error_status"] = "failed"
        data["error_stage"] = conn.error_stage
        data["error_details"] = conn.error_details
        return data

    contract = conn.contract
    data["normalized_contract"] = contract
    data["raw_chatbot_response"] = (contract.get("chatbotResponse") or {}).get("rawPayload")
    conn_tokens: int | None = (contract.get("tokenUsage") or {}).get("totalTokens")
    data["connector_token_count"] = conn_tokens

    ev = dispatch_evaluation(_evaluator_snapshot(job), contract, client=eval_client)
    if not ev.ok:
        data["error_status"] = "failed"
        data["error_stage"] = ev.error_stage
        data["error_details"] = ev.error_details
        data["total_token_count"] = conn_tokens
        return data

    body = ev.evaluation_result
    data["evaluation_agent_id"] = body.get("evaluationAgentId") or job.evaluation_agent_id
    data["evaluation_verdict"] = body.get("evaluationVerdict")
    data["evaluation_scores"] = body.get("evaluationScores")
    data["result_metadata"] = body.get("metadata")
    raw_intent = body.get("utteranceIntent")
    data["utterance_intent"] = raw_intent[:255] if isinstance(raw_intent, str) else raw_intent
    data["harness_annotations"] = ev.harness_annotations
    data["evaluation_timestamp"] = _parse_timestamp(body.get("evaluationTimestamp"))
    ev_tokens: int | None = (body.get("tokenUsage") or {}).get("totalTokens")
    data["evaluator_token_count"] = ev_tokens
    present = [t for t in (conn_tokens, ev_tokens) if t is not None]
    data["total_token_count"] = sum(present) if present else None
    return data
