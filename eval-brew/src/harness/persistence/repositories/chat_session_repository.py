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

    def _inactive_sessions_stmt(self, cutoff_dt: datetime):
        """SELECT statement for sessions inactive since cutoff_dt (single SQL roundtrip).

        A session is inactive when:
          - it has no in-progress turn, AND
          - its last activity (max turn completed_at/created_at, or session created_at) < cutoff.

        SQLite stores naive datetimes; timezone info is stripped from cutoff_dt.
        """
        from sqlalchemy import func

        cutoff = cutoff_dt.replace(tzinfo=None) if cutoff_dt.tzinfo else cutoff_dt

        max_turn_activity = (
            select(func.max(func.coalesce(ChatTurn.completed_at, ChatTurn.created_at)))
            .where(ChatTurn.session_id == ChatSession.chat_session_id)
            .correlate(ChatSession)
            .scalar_subquery()
        )
        last_activity = func.coalesce(max_turn_activity, ChatSession.created_at)

        has_in_progress = (
            select(ChatTurn.turn_id)
            .where(
                ChatTurn.session_id == ChatSession.chat_session_id,
                ChatTurn.status == "in_progress",
            )
            .correlate(ChatSession)
            .exists()
        )

        return select(ChatSession).where(~has_in_progress, last_activity < cutoff)

    def count_sessions_inactive_since(self, cutoff_dt: datetime) -> int:
        """Count sessions inactive since cutoff_dt (single SQL query)."""
        from sqlalchemy import func

        subq = self._inactive_sessions_stmt(cutoff_dt).subquery()
        return self._session.scalar(select(func.count()).select_from(subq)) or 0

    def delete_sessions_inactive_since(self, cutoff_dt: datetime) -> int:
        """Bulk-delete sessions inactive since cutoff_dt; returns deleted count."""
        sessions = list(self._session.scalars(self._inactive_sessions_stmt(cutoff_dt)))
        for s in sessions:
            self._session.delete(s)
        if sessions:
            self._session.flush()
        return len(sessions)

    def _no_in_progress_stmt(self):
        return ~(
            select(ChatTurn.turn_id)
            .where(
                ChatTurn.session_id == ChatSession.chat_session_id,
                ChatTurn.status == "in_progress",
            )
            .correlate(ChatSession)
            .exists()
        )

    def delete_errored_sessions(self, owner_oid: str | None = None) -> int:
        """Delete sessions that have at least one failed turn and no in_progress turn."""
        has_failed = (
            select(ChatTurn.turn_id)
            .where(
                ChatTurn.session_id == ChatSession.chat_session_id,
                ChatTurn.status == "failed",
            )
            .correlate(ChatSession)
            .exists()
        )
        stmt = select(ChatSession).where(self._no_in_progress_stmt(), has_failed)
        if owner_oid is not None:
            stmt = stmt.where(ChatSession.owner_oid == owner_oid)
        sessions = list(self._session.scalars(stmt))
        for s in sessions:
            self._session.delete(s)
        if sessions:
            self._session.flush()
        return len(sessions)

    def delete_all_inactive_sessions(self, owner_oid: str | None = None) -> int:
        """Delete all sessions with no in_progress turn."""
        stmt = select(ChatSession).where(self._no_in_progress_stmt())
        if owner_oid is not None:
            stmt = stmt.where(ChatSession.owner_oid == owner_oid)
        sessions = list(self._session.scalars(stmt))
        for s in sessions:
            self._session.delete(s)
        if sessions:
            self._session.flush()
        return len(sessions)

    def count_all_sessions(self) -> int:
        from sqlalchemy import func
        return self._session.scalar(select(func.count()).select_from(ChatSession)) or 0

    def count_all_turns(self) -> int:
        from sqlalchemy import func
        return self._session.scalar(select(func.count()).select_from(ChatTurn)) or 0

    def get_turn_counts(self, session_ids: list[str]) -> dict[str, int]:
        """Return {session_id: turn_count} for each given session_id (single GROUP BY query)."""
        from sqlalchemy import func

        if not session_ids:
            return {}
        rows = self._session.execute(
            select(ChatTurn.session_id, func.count(ChatTurn.turn_id).label("cnt"))
            .where(ChatTurn.session_id.in_(session_ids))
            .group_by(ChatTurn.session_id)
        ).all()
        counts = {row.session_id: row.cnt for row in rows}
        return {sid: counts.get(sid, 0) for sid in session_ids}

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
        conversation_id: str | None = None,
    ) -> None:
        """Batch write: mark turn completed, write result, write evaluation events.

        If conversation_id is provided, it is cached on the parent ChatSession so
        subsequent turns can forward it to the connector for conversation continuity.
        """
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

        if conversation_id is not None:
            session = self._session.get(ChatSession, turn.session_id)
            if session is not None:
                session.active_conversation_id = conversation_id

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
