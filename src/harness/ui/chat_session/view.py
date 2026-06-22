"""Session and turn projections for chat_session templates (017 US2)."""

from __future__ import annotations

from datetime import UTC, datetime

from harness.persistence.models.chat_session import ChatSession
from harness.persistence.models.chat_turn import ChatTurn


def _utcnow() -> datetime:
    return datetime.now(UTC)


def session_row_view(s: ChatSession) -> dict:
    """Flat dict for session list table rows."""
    turn_count = len(s.turns) if s.turns is not None else 0
    return {
        "chat_session_id": s.chat_session_id,
        "session_name": s.session_name,
        "owner_oid": s.owner_oid,
        "connector_name": s.connector_name or "—",
        "evaluator_name": s.evaluator_name or "—",
        "turn_count": turn_count,
        "created_at": s.created_at,
    }


def sort_sessions(rows: list[dict], sort: str, dir: str) -> list[dict]:
    """Sort session rows by *sort* column in *dir* direction."""
    allowed = {"session_name", "connector_name", "evaluator_name", "turn_count", "created_at"}
    if sort not in allowed:
        sort = "created_at"
    reverse = dir != "asc"
    return sorted(rows, key=lambda r: (r.get(sort) or ""), reverse=reverse)


def turn_view(turn: ChatTurn) -> dict:
    """Flat dict for rendering one turn in the chat interface."""
    result = turn.result
    events = turn.evaluation_events or []
    return {
        "turn_id": turn.turn_id,
        "status": turn.status,
        "user_message": turn.user_message,
        "created_at": turn.created_at,
        "completed_at": turn.completed_at,
        "assembled_response": result.assembled_response if result else None,
        "final_evaluation_result": result.final_evaluation_result if result else None,
        "error_stage": result.error_stage if result else None,
        "error_details": result.error_details if result else None,
        "evaluation_events": [
            {
                "event_type": ev.event_type,
                "payload": ev.payload,
                "sequence_number": ev.sequence_number,
            }
            for ev in events
        ],
    }
