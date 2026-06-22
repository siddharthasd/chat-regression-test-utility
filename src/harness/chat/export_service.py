"""Session export builder — JSON and CSV formats (017 US4)."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime

from harness.persistence.models.chat_session import ChatSession
from harness.persistence.models.chat_turn import ChatTurn


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _slug(name: str) -> str:
    """Convert session name to a safe filename slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "session"


def build_session_export(
    session: ChatSession,
    turns: list[ChatTurn],
    fmt: str,
) -> tuple[str, str, bytes]:
    """Build a session export.

    Returns (filename, mimetype, bytes).
    Credentials are NEVER included. In-progress turns are excluded.
    """
    finished_turns = [t for t in turns if t.status != "in_progress"]

    if fmt == "json":
        return _build_json(session, finished_turns)
    return _build_csv(session, finished_turns)


def _build_json(
    session: ChatSession, turns: list[ChatTurn]
) -> tuple[str, str, bytes]:
    slug = _slug(session.session_name)
    sid_short = session.chat_session_id[:8]
    filename = f"{slug}_{sid_short}.json"
    exported_at = _utcnow().isoformat() + "Z"

    turn_list = []
    for seq, turn in enumerate(turns, start=1):
        result = turn.result
        events = turn.evaluation_events or []
        turn_list.append(
            {
                "turn_id": turn.turn_id,
                "sequence": seq,
                "status": turn.status,
                "created_at": _iso(turn.created_at),
                "completed_at": _iso(turn.completed_at) if turn.completed_at else None,
                "user_message": turn.user_message,
                "assembled_response": result.assembled_response if result else None,
                "normalized_contract": result.normalized_contract if result else None,
                "evaluation_events": [
                    {
                        "sequence_number": ev.sequence_number,
                        "event_type": ev.event_type,
                        "payload": ev.payload,
                        "created_at": _iso(ev.created_at),
                    }
                    for ev in events
                ],
                "final_evaluation_result": result.final_evaluation_result if result else None,
                "error_stage": result.error_stage if result else None,
                "error_details": result.error_details if result else None,
            }
        )

    payload = {
        "session": {
            "session_id": session.chat_session_id,
            "session_name": session.session_name,
            "connector_name": session.connector_name,
            "evaluator_name": session.evaluator_name,
            "created_at": _iso(session.created_at),
            "exported_at": exported_at,
        },
        "total_turns": len(turn_list),
        "turns": turn_list,
    }
    content = json.dumps(payload, indent=2, default=str).encode("utf-8")
    return filename, "application/json", content


def _build_csv(
    session: ChatSession, turns: list[ChatTurn]
) -> tuple[str, str, bytes]:
    slug = _slug(session.session_name)
    sid_short = session.chat_session_id[:8]
    filename = f"{slug}_{sid_short}.csv"

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "session_id",
            "session_name",
            "connector_name",
            "evaluator_name",
            "turn_id",
            "sequence",
            "status",
            "created_at",
            "completed_at",
            "user_message",
            "assembled_response",
            "normalized_contract",
            "evaluation_events",
            "final_evaluation_result",
            "error_stage",
            "error_details",
        ]
    )
    for seq, turn in enumerate(turns, start=1):
        result = turn.result
        events = turn.evaluation_events or []
        writer.writerow(
            [
                session.chat_session_id,
                session.session_name,
                session.connector_name or "",
                session.evaluator_name or "",
                turn.turn_id,
                seq,
                turn.status,
                _iso(turn.created_at),
                _iso(turn.completed_at) if turn.completed_at else "",
                turn.user_message,
                result.assembled_response if result else "",
                json.dumps(result.normalized_contract, default=str) if (result and result.normalized_contract) else "",
                json.dumps(
                    [{"sequence_number": ev.sequence_number, "event_type": ev.event_type, "payload": ev.payload} for ev in events],
                    default=str,
                ),
                json.dumps(result.final_evaluation_result, default=str) if (result and result.final_evaluation_result) else "",
                result.error_stage if result else "",
                result.error_details if result else "",
            ]
        )
    return filename, "text/csv", buf.getvalue().encode("utf-8")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()
