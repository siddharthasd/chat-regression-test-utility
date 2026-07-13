"""ConnectorRegistryService — CRUD orchestration + business rules (FR-003/006/014/016/019).

Thin over 009's ConnectorRegistrationRepository; adds the rules the UI needs:
mode-change credential discard, list filtering/search, and hard-delete gating by
historical Job references.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.persistence.models import ConnectorRegistration
from harness.persistence.repositories import (
    ConnectorRegistrationRepository,
    JobRepository,
)
from harness.remote.oauth import invalidate_token


class RegistrationInUseError(Exception):
    """Hard-delete refused: historical Jobs reference this registration (FR-019)."""

    def __init__(self, connector_id: str, job_count: int) -> None:
        self.connector_id = connector_id
        self.job_count = job_count
        super().__init__(
            f"connector {connector_id!r} is referenced by {job_count} job(s); archive it instead"
        )


class ConnectorRegistryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = ConnectorRegistrationRepository(session)
        self._jobs = JobRepository(session)

    # ------------------------------------------------------------------ read
    def list_registrations(
        self, *, filter: str = "active", q: str | None = None
    ) -> list[ConnectorRegistration]:
        rows = list(self._session.scalars(select(ConnectorRegistration)))
        if filter == "active":
            rows = [r for r in rows if not r.archived]
        elif filter == "archived":
            rows = [r for r in rows if r.archived]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in r.display_name.lower()]
        rows.sort(key=lambda r: r.display_name.lower())
        return rows

    def get(self, connector_id: str) -> ConnectorRegistration | None:
        return self._repo.get(connector_id)

    def get_auth_descriptor_decrypted(self, connector_id: str) -> dict:
        return self._repo.get_auth_descriptor_decrypted(connector_id)

    # ------------------------------------------------------------------ write
    def create(self, payload: dict) -> ConnectorRegistration:
        """Create a registration; the repo assigns the id and encrypts secrets (FR-003)."""
        return self._repo.create(payload)

    def update(
        self, connector_id: str, payload: dict, *, replace_credential: bool
    ) -> ConnectorRegistration:
        """Update in place. Re-encrypts the descriptor only when the credential is
        replaced or the mode changed; otherwise the stored ciphertext is preserved
        (FR-006/011/012)."""
        existing = self._repo.get(connector_id)
        if existing is None:
            raise ValueError(f"connector not found: {connector_id!r}")
        new_mode = payload["auth_descriptor"]["mode"]
        mode_changed = new_mode != existing.auth_descriptor.get("mode")

        update_data: dict = {
            "display_name": payload["display_name"],
            "description": payload["description"],
            "endpoint_url": payload["endpoint_url"],
            "timeout_seconds": payload["timeout_seconds"],
            "expects_per_row_password": payload["expects_per_row_password"],
            "supports_sse": payload.get("supports_sse", False),
        }
        if replace_credential or mode_changed:
            update_data["auth_descriptor"] = payload["auth_descriptor"]
            # Drop any token cached under the old/new client-credentials key so a
            # rotated secret takes effect immediately (the cache key omits the
            # secret). No-ops for non-client-credentials descriptors. Key subfields
            # (tokenUrl/clientId/scope/audience) are plaintext in both forms.
            invalidate_token(existing.auth_descriptor or {})
            invalidate_token(payload["auth_descriptor"])
        return self._repo.update(connector_id, update_data)

    def archive(self, connector_id: str) -> None:
        self._repo.archive(connector_id)

    def restore(self, connector_id: str) -> None:
        self._repo.restore(connector_id)

    def count_referencing_jobs(self, connector_id: str) -> int:
        return self._jobs.count_by_connector_id(connector_id)

    def hard_delete(self, connector_id: str) -> None:
        """Remove permanently — refused if any historical Job references it (FR-019)."""
        count = self.count_referencing_jobs(connector_id)
        if count > 0:
            raise RegistrationInUseError(connector_id, count)
        self._repo.hard_delete(connector_id)
