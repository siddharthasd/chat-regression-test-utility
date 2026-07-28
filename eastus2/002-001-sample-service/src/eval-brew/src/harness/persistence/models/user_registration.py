"""UserRegistration ORM model — Azure AD user registry (015)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from harness.persistence.base import Base


class UserRegistration(Base):
    """One pre-registered user with their Azure OID linked after first login."""

    __tablename__ = "user_registration"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    azure_oid: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
