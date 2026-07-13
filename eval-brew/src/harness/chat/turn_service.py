"""TurnService — turn lifecycle management for live chat sessions (017 US3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from harness.persistence.models.chat_turn import ChatTurn
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TurnService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = ChatSessionRepository(session)

    def create_turn(self, session_id: str, user_message: str) -> ChatTurn:
        """Create a new in_progress turn; raise HTTP 409 if one is already active."""
        existing = self._repo.get_in_progress_turn(session_id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="Another turn is already in progress for this session. Wait for it to complete.",
            )
        turn = ChatTurn(
            turn_id=str(uuid.uuid4()),
            session_id=session_id,
            user_message=user_message.strip(),
            status="in_progress",
            created_at=_utcnow(),
        )
        return self._repo.create_turn(turn)

    def get_turn(self, turn_id: str, session_id: str) -> ChatTurn | None:
        return self._repo.get_turn(turn_id, session_id)
