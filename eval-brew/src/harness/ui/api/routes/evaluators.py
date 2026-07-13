"""Headless evaluator discovery endpoint (020, FR-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from harness.evaluator.registry import EvaluatorRegistryReader
from harness.persistence import get_session
from harness.ui.api.auth import require_api_auth
from harness.ui.api.schemas import EvaluatorListItem

router = APIRouter()


@router.get("/evaluators")
def list_evaluators(user: dict = Depends(require_api_auth)) -> dict:
    """Return all registered, active evaluators (no per-user filtering)."""
    with get_session() as session:
        entries = EvaluatorRegistryReader(session).list_active()
    return {
        "evaluators": [
            EvaluatorListItem(
                id=e.evaluation_agent_id,
                name=e.display_name,
                description=e.description,
                scoring_dimensions=list(e.declared_scoring_dimensions),
            ).model_dump()
            for e in entries
        ]
    }
