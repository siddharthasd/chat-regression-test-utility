"""ConnectorRegistrationRepository (009 FR-001a, contract repository-api.md).

Encrypts credential subfields on write; returns raw ciphertext on read except
via ``get_auth_descriptor_decrypted``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.persistence.models import ConnectorRegistration
from harness.persistence.repositories._auth_descriptor import (
    decrypt_descriptor,
    encrypt_descriptor,
)
from harness.persistence.repositories.types import (
    ConnectorRegistrationCreateData,
    ConnectorRegistrationUpdateData,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ConnectorRegistrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, data: ConnectorRegistrationCreateData) -> ConnectorRegistration:
        now = _utcnow()
        reg = ConnectorRegistration(
            connector_id=data.get("connector_id") or str(uuid.uuid4()),
            display_name=data["display_name"],
            description=data.get("description"),
            endpoint_url=data["endpoint_url"],
            auth_descriptor=encrypt_descriptor(data["auth_descriptor"]),
            timeout_seconds=data.get("timeout_seconds", 30),
            expects_per_row_password=data.get("expects_per_row_password", False),
            supports_sse=data.get("supports_sse", False),
            archived=False,
            created_at=now,
            updated_at=now,
        )
        self._session.add(reg)
        self._session.flush()
        return reg

    def get(self, connector_id: str) -> ConnectorRegistration | None:
        return self._session.get(ConnectorRegistration, connector_id)

    def get_active(self, *, supports_sse: bool | None = None) -> list[ConnectorRegistration]:
        stmt = select(ConnectorRegistration).where(ConnectorRegistration.archived.is_(False))
        if supports_sse is not None:
            stmt = stmt.where(ConnectorRegistration.supports_sse.is_(supports_sse))
        return list(self._session.scalars(stmt))

    def get_auth_descriptor_decrypted(self, connector_id: str) -> dict:
        return decrypt_descriptor(self._require(connector_id).auth_descriptor)

    def update(
        self, connector_id: str, data: ConnectorRegistrationUpdateData
    ) -> ConnectorRegistration:
        reg = self._require(connector_id)
        for field in (
            "display_name",
            "description",
            "endpoint_url",
            "timeout_seconds",
            "expects_per_row_password",
            "supports_sse",
        ):
            if field in data:
                setattr(reg, field, data[field])
        if "auth_descriptor" in data:
            reg.auth_descriptor = encrypt_descriptor(data["auth_descriptor"])
        reg.updated_at = _utcnow()
        self._session.flush()
        return reg

    def archive(self, connector_id: str) -> None:
        reg = self._require(connector_id)
        if not reg.archived:
            reg.archived = True
            reg.archived_at = _utcnow()
            reg.updated_at = _utcnow()
        self._session.flush()

    def restore(self, connector_id: str) -> None:
        reg = self._require(connector_id)
        reg.archived = False
        reg.archived_at = None
        reg.updated_at = _utcnow()
        self._session.flush()

    def hard_delete(self, connector_id: str) -> None:
        self._session.delete(self._require(connector_id))
        self._session.flush()

    def _require(self, connector_id: str) -> ConnectorRegistration:
        reg = self._session.get(ConnectorRegistration, connector_id)
        if reg is None:
            raise ValueError(f"connector not found: {connector_id!r}")
        return reg
