"""EvaluationAgentRegistrationRepository (009 FR-001b, contract repository-api.md).

Symmetric to ConnectorRegistrationRepository, keyed by ``evaluation_agent_id``,
plus ``get_declared_dimensions`` for the detail view / export column order.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.persistence.models import EvaluationAgentRegistration
from harness.persistence.repositories._auth_descriptor import (
    decrypt_descriptor,
    encrypt_descriptor,
)
from harness.persistence.repositories.types import (
    EvaluationAgentRegistrationCreateData,
    EvaluationAgentRegistrationUpdateData,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EvaluationAgentRegistrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self, data: EvaluationAgentRegistrationCreateData
    ) -> EvaluationAgentRegistration:
        now = _utcnow()
        reg = EvaluationAgentRegistration(
            evaluation_agent_id=data.get("evaluation_agent_id") or str(uuid.uuid4()),
            display_name=data["display_name"],
            description=data["description"],
            endpoint_url=data["endpoint_url"],
            auth_descriptor=encrypt_descriptor(data["auth_descriptor"]),
            timeout_seconds=data.get("timeout_seconds", 60),
            declared_scoring_dimensions=data.get("declared_scoring_dimensions", []),
            score_scale_min=data.get("score_scale_min"),
            score_scale_max=data.get("score_scale_max"),
            supports_sse=data.get("supports_sse", False),
            archived=False,
            created_at=now,
            updated_at=now,
        )
        self._session.add(reg)
        self._session.flush()
        return reg

    def get(self, evaluation_agent_id: str) -> EvaluationAgentRegistration | None:
        return self._session.get(EvaluationAgentRegistration, evaluation_agent_id)

    def get_active(self, *, supports_sse: bool | None = None) -> list[EvaluationAgentRegistration]:
        stmt = select(EvaluationAgentRegistration).where(EvaluationAgentRegistration.archived.is_(False))
        if supports_sse is not None:
            stmt = stmt.where(EvaluationAgentRegistration.supports_sse.is_(supports_sse))
        return list(self._session.scalars(stmt))

    def get_auth_descriptor_decrypted(self, evaluation_agent_id: str) -> dict:
        return decrypt_descriptor(self._require(evaluation_agent_id).auth_descriptor)

    def get_declared_dimensions(self, evaluation_agent_id: str) -> list[str]:
        return list(self._require(evaluation_agent_id).declared_scoring_dimensions)

    def update(
        self, evaluation_agent_id: str, data: EvaluationAgentRegistrationUpdateData
    ) -> EvaluationAgentRegistration:
        reg = self._require(evaluation_agent_id)
        for field in (
            "display_name",
            "description",
            "endpoint_url",
            "timeout_seconds",
            "declared_scoring_dimensions",
            "supports_sse",
            "score_scale_min",
            "score_scale_max",
        ):
            if field in data:
                setattr(reg, field, data[field])
        if "auth_descriptor" in data:
            reg.auth_descriptor = encrypt_descriptor(data["auth_descriptor"])
        reg.updated_at = _utcnow()
        self._session.flush()
        return reg

    def archive(self, evaluation_agent_id: str) -> None:
        reg = self._require(evaluation_agent_id)
        if not reg.archived:
            reg.archived = True
            reg.archived_at = _utcnow()
            reg.updated_at = _utcnow()
        self._session.flush()

    def restore(self, evaluation_agent_id: str) -> None:
        reg = self._require(evaluation_agent_id)
        reg.archived = False
        reg.archived_at = None
        reg.updated_at = _utcnow()
        self._session.flush()

    def hard_delete(self, evaluation_agent_id: str) -> None:
        self._session.delete(self._require(evaluation_agent_id))
        self._session.flush()

    def _require(self, evaluation_agent_id: str) -> EvaluationAgentRegistration:
        reg = self._session.get(EvaluationAgentRegistration, evaluation_agent_id)
        if reg is None:
            raise ValueError(f"evaluator not found: {evaluation_agent_id!r}")
        return reg
