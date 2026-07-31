"""Evaluator Registry read facade (FR-008-013, R6).

Read-only view over 009's EvaluationAgentRegistrationRepository. Write surface
(create/edit/archive/restore/hard-delete) lives in 014.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from harness.persistence.models import EvaluationAgentRegistration
from harness.persistence.repositories import EvaluationAgentRegistrationRepository


@dataclass(frozen=True)
class EvaluatorListEntry:
    """Minimal tuple for the wizard's Step 4 dropdown (FR-009a)."""

    evaluation_agent_id: str
    display_name: str
    description: str
    declared_scoring_dimensions: list[str]


class EvaluatorRegistryReader:
    """Read API consumed identically by wizard / orchestrator / detail / export (FR-010)."""

    def __init__(self, session: Session) -> None:
        self._repo = EvaluationAgentRegistrationRepository(session)

    def list_active(self, *, supports_sse: bool | None = None) -> list[EvaluatorListEntry]:
        return [
            EvaluatorListEntry(
                evaluation_agent_id=r.evaluation_agent_id,
                display_name=r.display_name,
                description=r.description,
                declared_scoring_dimensions=list(r.declared_scoring_dimensions),
            )
            for r in self._repo.get_active(supports_sse=supports_sse)
        ]

    def get(self, evaluation_agent_id: str) -> EvaluationAgentRegistration | None:
        return self._repo.get(evaluation_agent_id)

    def get_declared_dimensions(self, evaluation_agent_id: str) -> list[str]:
        return self._repo.get_declared_dimensions(evaluation_agent_id)
