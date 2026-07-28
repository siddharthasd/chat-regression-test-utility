"""UserRegistrationRepository — CRUD for the user_registration table (015)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.persistence.models.user_registration import UserRegistration


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserRegistrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------------------------------------------------------------------- read

    def find_by_oid(self, oid: str) -> UserRegistration | None:
        return self._session.scalar(
            select(UserRegistration).where(UserRegistration.azure_oid == oid)
        )

    def find_by_email(self, email: str) -> UserRegistration | None:
        return self._session.scalar(
            select(UserRegistration).where(UserRegistration.email == email.lower())
        )

    def find_unlinked_by_email(self, email: str) -> UserRegistration | None:
        """Return a registration whose OID hasn't been linked yet (first login)."""
        return self._session.scalar(
            select(UserRegistration).where(
                UserRegistration.email == email.lower(),
                UserRegistration.azure_oid.is_(None),
            )
        )

    def find_unlinked_by_any_email(self, emails: list[str]) -> UserRegistration | None:
        """Return the first unlinked registration matching any of the given email
        addresses (first login, multi-claim SSO fallback).

        A single IN query avoids one round-trip per candidate.
        """
        if not emails:
            return None
        lowered = [e.lower() for e in emails]
        return self._session.scalar(
            select(UserRegistration).where(
                UserRegistration.email.in_(lowered),
                UserRegistration.azure_oid.is_(None),
            )
        )

    def get(self, reg_id: str) -> UserRegistration | None:
        return self._session.get(UserRegistration, reg_id)

    def list_all(self) -> list[UserRegistration]:
        return list(
            self._session.scalars(
                select(UserRegistration).order_by(UserRegistration.registered_at)
            )
        )

    # ---------------------------------------------------------------------- write

    def create(self, email: str, role: str, display_name: str | None = None) -> UserRegistration:
        reg = UserRegistration(
            id=str(uuid.uuid4()),
            email=email.lower(),
            role=role,
            display_name=display_name,
            registered_at=_utcnow(),
        )
        self._session.add(reg)
        self._session.flush()
        return reg

    def link_oid(self, reg: UserRegistration, oid: str, display_name: str) -> None:
        reg.azure_oid = oid
        reg.display_name = display_name
        self._session.flush()

    def update_last_login(self, reg: UserRegistration) -> None:
        reg.last_login_at = _utcnow()
        self._session.flush()

    def update_role(self, reg: UserRegistration, role: str) -> None:
        reg.role = role
        self._session.flush()

    def delete(self, reg: UserRegistration) -> None:
        self._session.delete(reg)
        self._session.flush()
