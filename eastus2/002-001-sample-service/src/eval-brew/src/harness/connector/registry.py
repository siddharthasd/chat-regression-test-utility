"""Connector Registry read facade (FR-009-011, R6).

A thin read-only view over 009's ConnectorRegistrationRepository. The write
surface (create/edit/archive/restore/hard-delete) lives in 013.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from harness.persistence.models import ConnectorRegistration
from harness.persistence.repositories import ConnectorRegistrationRepository


@dataclass(frozen=True)
class ConnectorListEntry:
    """Minimal tuple for the wizard's Step 3 dropdown (FR-010a)."""

    connector_id: str
    display_name: str
    description: str | None
    expects_per_row_password: bool


class ConnectorRegistryReader:
    """Read API consumed identically by the wizard and the orchestrator (FR-011)."""

    def __init__(self, session: Session) -> None:
        self._repo = ConnectorRegistrationRepository(session)

    def list_active(self) -> list[ConnectorListEntry]:
        """Active (non-archived) connectors as minimal entries (FR-010a)."""
        return [
            ConnectorListEntry(
                connector_id=r.connector_id,
                display_name=r.display_name,
                description=r.description,
                expects_per_row_password=r.expects_per_row_password,
            )
            for r in self._repo.get_active()
        ]

    def get(self, connector_id: str) -> ConnectorRegistration | None:
        """Full registration record (ciphertext intact) by id (FR-010b)."""
        return self._repo.get(connector_id)
