"""ChatSessionService — creates and manages live chat sessions (017 US1).

Handles credential encryption, connector/evaluator snapshotting, and persistence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from harness.persistence.encryption import decrypt_credential, encrypt_credential
from harness.persistence.models.chat_session import ChatSession
from harness.persistence.models.connector_registration import ConnectorRegistration
from harness.persistence.models.evaluator_registration import EvaluationAgentRegistration
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatSessionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = ChatSessionRepository(session)

    def create_session(
        self,
        name: str,
        connector_id: str,
        test_id: str,
        password: str,
        evaluator_id: str,
        owner_oid: str,
    ) -> ChatSession:
        """Create and persist a new ChatSession with encrypted credentials.

        Snapshots connector and evaluator fields from their registrations so the
        session remains self-contained even if the registrations are later edited.
        """
        connector = self._session.get(ConnectorRegistration, connector_id)
        if connector is None or connector.archived:
            raise ValueError(f"connector not found or archived: {connector_id!r}")
        if not connector.supports_sse:
            raise ValueError(f"connector {connector_id!r} does not support SSE streaming")

        evaluator = self._session.get(EvaluationAgentRegistration, evaluator_id)
        if evaluator is None or evaluator.archived:
            raise ValueError(f"evaluator not found or archived: {evaluator_id!r}")
        if not evaluator.supports_sse:
            raise ValueError(f"evaluator {evaluator_id!r} does not support SSE streaming")

        chat_session = ChatSession(
            chat_session_id=str(uuid.uuid4()),
            session_name=name.strip(),
            owner_oid=owner_oid,
            created_at=_utcnow(),
            test_id_enc=encrypt_credential(test_id),
            test_password_enc=encrypt_credential(password),
            # Connector snapshot
            connector_id=connector.connector_id,
            connector_name=connector.display_name,
            connector_endpoint_url=connector.endpoint_url,
            connector_auth_descriptor=connector.auth_descriptor,
            connector_timeout_seconds=connector.timeout_seconds,
            # Evaluator snapshot
            evaluator_id=evaluator.evaluation_agent_id,
            evaluator_name=evaluator.display_name,
            evaluator_endpoint_url=evaluator.endpoint_url,
            evaluator_auth_descriptor=evaluator.auth_descriptor,
            evaluator_timeout_seconds=evaluator.timeout_seconds,
            evaluator_declared_scoring_dimensions=evaluator.declared_scoring_dimensions,
        )
        return self._repo.create_session(chat_session)

    def get_session(
        self, session_id: str, owner_oid: str | None = None
    ) -> ChatSession | None:
        return self._repo.get_session(session_id, owner_oid)

    def decrypt_test_id(self, chat_session: ChatSession) -> str:
        return decrypt_credential(chat_session.test_id_enc)

    def decrypt_password(self, chat_session: ChatSession) -> str:
        return decrypt_credential(chat_session.test_password_enc)
