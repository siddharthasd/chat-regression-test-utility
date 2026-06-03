"""Re-exports for all persistence ORM models.

Importing this module populates ``Base.metadata`` with every entity table —
relied on by the Alembic migration chain and the test fixtures.
"""

from __future__ import annotations

from harness.persistence.models.connector_registration import ConnectorRegistration
from harness.persistence.models.evaluation_result import EvaluationResult
from harness.persistence.models.evaluator_registration import EvaluationAgentRegistration
from harness.persistence.models.job import Job
from harness.persistence.models.utterance import Utterance

__all__ = [
    "ConnectorRegistration",
    "EvaluationAgentRegistration",
    "EvaluationResult",
    "Job",
    "Utterance",
]
