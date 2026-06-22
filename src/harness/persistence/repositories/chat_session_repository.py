"""ChatSessionRepository — CRUD for live chat sessions, turns, and events (017)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.persistence.models.chat_session import ChatSession
from harness.persistence.models.chat_turn import ChatTurn
from harness.persistence.models.chat_turn_result import ChatTurnResult
from harness.persistence.models.evaluation_event import EvaluationEvent


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ----------------------------------------------------------------- sessions

    def create_session(self, chat_session: ChatSession) -> ChatSession:
        self._session.add(chat_session)
        self._session.flush()
        return chat_session

    def get_session(
        self, session_id: str, owner_oid: str | None = None
    ) -> ChatSession | None:
        """Fetch by ID; optionally scope to owner (pass None for admin access)."""
        s = self._session.get(ChatSession, session_id)
        if s is None:
            return None
        if owner_oid is not None and s.owner_oid != owner_oid:
            return None
        return s

    def list_sessions_for_owner(self, owner_oid: str) -> list[ChatSession]:
        return list(
            self._session.scalars(
                select(ChatSession)
                .where(ChatSession.owner_oid == owner_oid)
                .order_by(ChatSession.created_at.desc())
            )
        )

    def list_all_sessions(self) -> list[ChatSession]:
        return list(
            self._session.scalars(select(ChatSession).order_by(ChatSession.created_at.desc()))
        )

    def delete_session(self, session_id: str) -> None:
        s = self._session.get(ChatSession, session_id)
        if s is not None:
            self._session.delete(s)
            self._session.flush()

    def count_sessions_inactive_since(self, cutoff_dt: datetime) -> int:
        """Count sessions whose most-recent turn completed before *cutoff_dt*,
        or sessions with no turns whose created_at is before *cutoff_dt*.
        Sessions with an in-progress turn are excluded."""
        all_sessions = self.list_all_sessions()
        count = 0
        for s in all_sessions:
            if self._is_inactive_since(s, cutoff_dt):
                count += 1
        return count

    def delete_sessions_inactive_since(self, cutoff_dt: datetime) -> int:
        """Bulk-delete sessions inactive since *cutoff_dt*; skip in-progress ones."""
        all_sessions = self.list_all_sessions()
        deleted = 0
        for s in all_sessions:
            if self._is_inactive_since(s, cutoff_dt):
                self._session.delete(s)
                deleted += 1
        if deleted:
            self._session.flush()
        return deleted

    def count_all_sessions(self) -> int:
        from sqlalchemy import func
        return self._session.scalar(select(func.count()).select_from(ChatSession)) or 0

    def count_all_turns(self) -> int:
        from sqlalchemy import func
        return self._session.scalar(select(func.count()).select_from(ChatTurn)) or 0

    def _is_inactive_since(self, s: ChatSession, cutoff_dt: datetime) -> bool:
        in_progress = self.get_in_progress_turn(s.chat_session_id)
        if in_progress is not None:
            return False
        # Find the most recent completed_at among turns
        turns = list(
            self._session.scalars(
                select(ChatTurn)
                .where(ChatTurn.session_id == s.chat_session_id)
                .order_by(ChatTurn.completed_at.desc())
            )
        )
        if not turns:
            # No turns — use session creation time
            created = s.created_at
            if created.tzinfo is None:
                from datetime import timezone
                created = created.replace(tzinfo=timezone.utc)
            return created < cutoff_dt
        last_turn = turns[0]
        last_activity = last_turn.completed_at or last_turn.created_at
        if last_activity.tzinfo is None:
            from datetime import timezone
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        return last_activity < cutoff_dt

    # ----------------------------------------------------------------- turns

    def create_turn(self, turn: ChatTurn) -> ChatTurn:
        self._session.add(turn)
        self._session.flush()
        return turn

    def get_turn(self, turn_id: str, session_id: str) -> ChatTurn | None:
        return self._session.scalar(
            select(ChatTurn).where(
                ChatTurn.turn_id == turn_id, ChatTurn.session_id == session_id
            )
        )

    def get_in_progress_turn(self, session_id: str) -> ChatTurn | None:
        return self._session.scalar(
            select(ChatTurn).where(
                ChatTurn.session_id == session_id, ChatTurn.status == "in_progress"
            )
        )

    def complete_turn(
        self,
        turn_id: str,
        assembled_response: str,
        normalized_contract: dict | None,
        final_evaluation_result: dict | None,
        evaluation_events: list[dict],
    ) -> None:
        """Batch write: mark turn completed, write result, write evaluation events."""
        turn = self._session.get(ChatTurn, turn_id)
        if turn is None:
            return
        now = _utcnow()
        turn.status = "completed"
        turn.completed_at = now

        result = ChatTurnResult(
            turn_result_id=str(uuid.uuid4()),
            turn_id=turn_id,
            assembled_response=assembled_response,
            normalized_contract=normalized_contract,
            final_evaluation_result=final_evaluation_result,
            error_stage=None,
            error_details=None,
        )
        self._session.add(result)

        for seq, ev in enumerate(evaluation_events, start=1):
            self._session.add(
                EvaluationEvent(
                    event_id=str(uuid.uuid4()),
                    turn_id=turn_id,
                    event_type=ev["event_type"],
                    payload=ev["payload"],
                    sequence_number=seq,
                    created_at=now,
                )
            )
        self._session.flush()

    def fail_turn(
        self,
        turn_id: str,
        error_stage: str,
        error_details: str,
        assembled_response: str | None = None,
        evaluation_events: list[dict] | None = None,
    ) -> None:
        """Batch write: mark turn failed, write result with error info."""
        turn = self._session.get(ChatTurn, turn_id)
        if turn is None:
            return
        now = _utcnow()
        turn.status = "failed"
        turn.completed_at = now

        result = ChatTurnResult(
            turn_result_id=str(uuid.uuid4()),
            turn_id=turn_id,
            assembled_response=assembled_response,
            normalized_contract=None,
            final_evaluation_result=None,
            error_stage=error_stage,
            error_details=error_details,
        )
        self._session.add(result)

        for seq, ev in enumerate(evaluation_events or [], start=1):
            self._session.add(
                EvaluationEvent(
                    event_id=str(uuid.uuid4()),
                    turn_id=turn_id,
                    event_type=ev["event_type"],
                    payload=ev["payload"],
                    sequence_number=seq,
                    created_at=now,
                )
            )
        self._session.flush()

    def recover_stale_turns(self) -> int:
        """Startup recovery: flip all in_progress turns to failed.

        Returns the number of turns recovered.
        """
        stale = list(
            self._session.scalars(
                select(ChatTurn).where(ChatTurn.status == "in_progress")
            )
        )
        now = _utcnow()
        for turn in stale:
            turn.status = "failed"
            turn.completed_at = now
            # Write a result if one doesn't already exist
            existing_result = self._session.scalar(
                select(ChatTurnResult).where(ChatTurnResult.turn_id == turn.turn_id)
            )
            if existing_result is None:
                self._session.add(
                    ChatTurnResult(
                        turn_result_id=str(uuid.uuid4()),
                        turn_id=turn.turn_id,
                        assembled_response=None,
                        normalized_contract=None,
                        final_evaluation_result=None,
                        error_stage="server_restart",
                        error_details="Server restarted while turn was in progress",
                    )
                )
        if stale:
            self._session.flush()
        return len(stale)
