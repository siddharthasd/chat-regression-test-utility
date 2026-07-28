"""Dispatch input/output types for the evaluator client (contracts/client-api.md)."""

from __future__ import annotations

from dataclasses import dataclass

#: Closed verdict enum (FR-004).
VERDICTS = frozenset({"pass", "fail", "warn"})


@dataclass(frozen=True)
class EvaluatorSnapshot:
    """Evaluator config snapshotted onto a Job (parent FR-023). Built by 012."""

    evaluation_agent_id: str
    endpoint_url: str
    auth_descriptor: dict  # ciphertext subfields (verbatim from the Job snapshot)
    timeout_seconds: int
    declared_scoring_dimensions: list[str]


@dataclass(frozen=True)
class EvaluatorResult:
    """Outcome of one evaluator dispatch: a validated result or a categorized failure."""

    ok: bool
    evaluation_result: dict | None = None  # evaluator-emitted, FR-005b-validated
    harness_annotations: dict | None = None  # {"unexpected_score_dimensions": [...]}
    error_stage: str | None = None  # evaluator_auth|transport|response|result
    error_details: str | None = None
    status_code: int | None = None
