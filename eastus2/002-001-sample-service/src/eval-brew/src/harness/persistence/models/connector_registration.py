"""ConnectorRegistration ORM model — a registered remote connector (009 FR-001a).

Credential subfields within ``auth_descriptor`` are stored as plaintext.
Managed by the CRUD module 013; snapshotted onto each Job at job-creation time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from harness.persistence.base import Base


class ConnectorRegistration(Base):
    """A persisted record describing a remote connector service."""

    __tablename__ = "connector_registration"

    connector_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    endpoint_url: Mapped[str] = mapped_column(String, nullable=False)
    auth_descriptor: Mapped[dict] = mapped_column(JSON, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    expects_per_row_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    supports_sse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
