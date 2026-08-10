"""EvaluatorRegistryService — CRUD orchestration + business rules (FR-003/006/019/024).

Mirrors connector_registry.service over 009's EvaluationAgentRegistrationRepository.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.persistence.encryption import decrypt_descriptor
from harness.persistence.models import EvaluationAgentRegistration
from harness.persistence.repositories import (
    EvaluationAgentRegistrationRepository,
    JobRepository,
)
from harness.remote.oauth import invalidate_token


class RegistrationInUseError(Exception):
    """Hard-delete refused: historical Jobs reference this evaluator (FR-024)."""

    def __init__(self, evaluation_agent_id: str, job_count: int) -> None:
        self.evaluation_agent_id = evaluation_agent_id
        self.job_count = job_count
        super().__init__(
            f"evaluator {evaluation_agent_id!r} is referenced by {job_count} job(s); "
            "archive it instead"
        )


class EvaluatorRegistryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = EvaluationAgentRegistrationRepository(session)
        self._jobs = JobRepository(session)

    # ------------------------------------------------------------------ read
    def list_registrations(
        self, *, filter: str = "active", q: str | None = None
    ) -> list[EvaluationAgentRegistration]:
        rows = list(self._session.scalars(select(EvaluationAgentRegistration)))
        if filter == "active":
            rows = [r for r in rows if not r.archived]
        elif filter == "archived":
            rows = [r for r in rows if r.archived]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in r.display_name.lower()]
        rows.sort(key=lambda r: r.display_name.lower())
        return rows

    def get(self, evaluation_agent_id: str) -> EvaluationAgentRegistration | None:
        return self._repo.get(evaluation_agent_id)

    def get_auth_descriptor_decrypted(self, evaluation_agent_id: str) -> dict:
        return self._repo.get_auth_descriptor_decrypted(evaluation_agent_id)

    # ------------------------------------------------------------------ write
    def create(self, payload: dict) -> EvaluationAgentRegistration:
        return self._repo.create(payload)

    def update(
        self, evaluation_agent_id: str, payload: dict, *, replace_credential: bool
    ) -> EvaluationAgentRegistration:
        existing = self._repo.get(evaluation_agent_id)
        if existing is None:
            raise ValueError(f"evaluator not found: {evaluation_agent_id!r}")
        new_mode = payload["auth_descriptor"]["mode"]
        mode_changed = new_mode != existing.auth_descriptor.get("mode")

        update_data: dict = {
            "display_name": payload["display_name"],
            "description": payload["description"],
            "endpoint_url": payload["endpoint_url"],
            "timeout_seconds": payload["timeout_seconds"],
            "declared_scoring_dimensions": payload["declared_scoring_dimensions"],
            "supports_sse": payload.get("supports_sse", False),
            "score_scale_min": payload.get("score_scale_min"),
            "score_scale_max": payload.get("score_scale_max"),
            "scoring_thresholds": payload.get("scoring_thresholds"),
        }
        if replace_credential or mode_changed:
            update_data["auth_descriptor"] = payload["auth_descriptor"]
        else:
            # Non-secret fields (tokenUrl, clientId, scope, audience) may have
            # changed. Decrypt the stored secret, merge it with the new payload so
            # the repo re-encrypts a complete descriptor without losing the secret.
            stored = decrypt_descriptor(existing.auth_descriptor or {})
            merged = dict(payload["auth_descriptor"])
            for key in ("clientSecret", "credential", "password"):
                val = stored.get(key)
                if val:
                    merged[key] = val
                else:
                    merged.pop(key, None)
            update_data["auth_descriptor"] = merged
        # Invalidate OAuth token cache whenever auth_descriptor changes — the cache
        # key covers tokenUrl/clientId/scope/audience, not just the secret.
        invalidate_token(existing.auth_descriptor or {})
        invalidate_token(update_data["auth_descriptor"])
        return self._repo.update(evaluation_agent_id, update_data)

    def archive(self, evaluation_agent_id: str) -> None:
        self._repo.archive(evaluation_agent_id)

    def restore(self, evaluation_agent_id: str) -> None:
        self._repo.restore(evaluation_agent_id)

    def count_referencing_jobs(self, evaluation_agent_id: str) -> int:
        return self._jobs.count_by_evaluation_agent_id(evaluation_agent_id)

    def hard_delete(self, evaluation_agent_id: str) -> None:
        count = self.count_referencing_jobs(evaluation_agent_id)
        if count > 0:
            raise RegistrationInUseError(evaluation_agent_id, count)
        self._repo.hard_delete(evaluation_agent_id)
