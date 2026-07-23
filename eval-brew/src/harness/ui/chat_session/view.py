"""Session and turn projections for chat_session templates (017 US2, 019)."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime

from harness.persistence.models.chat_session import ChatSession
from harness.persistence.models.chat_turn import ChatTurn

_TRUNCATE = 200
_VERDICT_ORDER = {"fail": 0, "warn": 1, "pass": 2}


def _extract_tokens(data: dict | None) -> int | None:
    if not data:
        return None
    usage = data.get("tokenUsage") or {}
    total = usage.get("totalTokens")
    if total is None:
        prompt = usage.get("promptTokens")
        completion = usage.get("completionTokens")
        if prompt is not None or completion is not None:
            total = (prompt or 0) + (completion or 0)
    return total


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    return text if len(text) <= _TRUNCATE else text[:_TRUNCATE] + "…"


def _sanitise_filename(name: str, fallback_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug if slug else f"session-{fallback_id[:8]}"


def session_row_view(s: ChatSession, turn_count: int = 0) -> dict:
    """Flat dict for session list table rows."""
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
    conn_tokens = _extract_tokens(result.normalized_contract if result else None)
    ev_tokens = _extract_tokens(result.final_evaluation_result if result else None)
    if conn_tokens is not None or ev_tokens is not None:
        total_tokens = (conn_tokens or 0) + (ev_tokens or 0)
    else:
        total_tokens = None
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
        "connector_token_count": conn_tokens,
        "evaluator_token_count": ev_tokens,
        "total_token_count": total_tokens,
        "evaluation_events": [
            {
                "event_type": ev.event_type,
                "payload": ev.payload,
                "sequence_number": ev.sequence_number,
            }
            for ev in events
        ],
    }


# ---------------------------------------------------------------------------
# 019: analytics view helpers


def score_entries_from_turns(turns: list) -> list:
    """Map ChatTurn list (completed/failed only) to ScoreEntry list for RunAnalytics."""
    from harness.ui.detail.analytics import ScoreEntry

    entries = []
    for turn in turns:
        result = turn.result
        # Per FR-023: only completed turns with a non-null evaluationResult contribute to scores.
        is_error = turn.status == "failed" or not (result and result.final_evaluation_result)
        final = result.final_evaluation_result if (result and not is_error) else None
        overall_verdict = (final or {}).get("overallVerdict") if not is_error else None
        if overall_verdict:
            overall_verdict = overall_verdict.lower()
        params = ((final or {}).get("parameters") or []) if not is_error else []

        for p in params:
            if not isinstance(p, dict):
                continue
            entries.append(
                ScoreEntry(
                    parameter_name=p.get("parameter_name", ""),
                    score=float(p.get("score") or 0.0),
                    reasoning=p.get("reasoning") or "",
                    verdict=p.get("verdict"),
                    overall_verdict=overall_verdict,
                    error=is_error,
                    unit_id=turn.turn_id,
                    utterance_intent=None,
                )
            )
        if not params:
            entries.append(
                ScoreEntry(
                    parameter_name="",
                    score=0.0,
                    reasoning="",
                    verdict=None,
                    overall_verdict=overall_verdict,
                    error=is_error,
                    unit_id=turn.turn_id,
                    utterance_intent=None,
                )
            )
    return entries


def _turn_score_cells(final_result: dict | None, declared_dims: list[str]) -> list[dict]:
    if final_result is None:
        return [{"name": d, "score": None, "reasoning": "", "verdict": None} for d in declared_dims]
    params = final_result.get("parameters") or []
    by_name = {
        p["parameter_name"]: p
        for p in params
        if isinstance(p, dict) and "parameter_name" in p
    }
    cells = []
    for d in declared_dims:
        p = by_name.get(d)
        if p is None:
            cells.append({"name": d, "score": None, "reasoning": "", "verdict": None})
        else:
            cells.append(
                {
                    "name": d,
                    "score": p.get("score"),
                    "reasoning": p.get("reasoning") or "",
                    "verdict": p.get("verdict"),
                }
            )
    for p in params:
        name = p.get("parameter_name") if isinstance(p, dict) else None
        if name and name not in declared_dims:
            cells.append(
                {
                    "name": name,
                    "score": p.get("score"),
                    "reasoning": p.get("reasoning") or "",
                    "verdict": p.get("verdict"),
                    "unexpected": True,
                }
            )
    return cells


def turn_explorer_view(turn: ChatTurn, turn_index: int, declared_dims: list[str]) -> dict:
    result = turn.result
    is_error = turn.status == "failed" or not (result and result.final_evaluation_result)
    final = result.final_evaluation_result if (result and not is_error) else None
    overall_verdict = (final or {}).get("overallVerdict") if final else None
    if overall_verdict:
        overall_verdict = overall_verdict.lower()
    assembled = result.assembled_response if result else None

    return {
        "turn_index": turn_index,
        "turn_id": turn.turn_id,
        "status": turn.status,
        "user_message": turn.user_message,
        "user_message_short": _truncate(turn.user_message),
        "assembled_response": assembled,
        "assembled_response_short": _truncate(assembled),
        "verdict": overall_verdict,
        "error_stage": result.error_stage if result else None,
        "error_details": result.error_details if result else None,
        "score_cells": _turn_score_cells(final, declared_dims),
        "normalized_contract": result.normalized_contract if result else None,
        "final_evaluation_result": final,
    }


def results_csv_builder(session: ChatSession, turns: list) -> tuple[str, str]:
    filename_base = _sanitise_filename(
        session.session_name or "", session.chat_session_id
    )
    filename = f"{filename_base}-results.csv"

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "turnIndex",
            "userMessage",
            "assembledResponse",
            "overallVerdict",
            "parameterName",
            "score",
            "verdict",
            "reasoning",
        ]
    )
    for i, turn in enumerate(turns, start=1):
        result = turn.result
        is_error = turn.status == "failed" or not (result and result.final_evaluation_result)
        final = result.final_evaluation_result if (result and not is_error) else None
        if is_error:
            overall_verdict = (result.error_stage or "failed") if result else "failed"
        else:
            overall_verdict = ((final or {}).get("overallVerdict") or "").lower()
        assembled = result.assembled_response if result else ""
        params = (final or {}).get("parameters") or []
        if not params:
            writer.writerow(
                [i, turn.user_message, assembled or "", overall_verdict, "", "", "", ""]
            )
        else:
            for p in params:
                if not isinstance(p, dict):
                    continue
                writer.writerow(
                    [
                        i,
                        turn.user_message,
                        assembled or "",
                        overall_verdict,
                        p.get("parameter_name", ""),
                        p.get("score", ""),
                        p.get("verdict") or "",
                        p.get("reasoning", ""),
                    ]
                )
    return filename, buf.getvalue()


def results_json_builder(session: ChatSession, turns: list) -> tuple[str, str]:
    filename_base = _sanitise_filename(
        session.session_name or "", session.chat_session_id
    )
    filename = f"{filename_base}-results.json"

    result_array = []
    for i, turn in enumerate(turns, start=1):
        result = turn.result
        is_error = turn.status == "failed" or not (result and result.final_evaluation_result)
        final = result.final_evaluation_result if (result and not is_error) else None
        params = []
        if final:
            for p in (final.get("parameters") or []):
                if not isinstance(p, dict):
                    continue
                entry: dict = {
                    "parameter_name": p.get("parameter_name", ""),
                    "score": p.get("score"),
                    "reasoning": p.get("reasoning") or "",
                }
                if "verdict" in p:
                    entry["verdict"] = p["verdict"]
                params.append(entry)

        raw_verdict = (final or {}).get("overallVerdict") if not is_error else None
        result_array.append(
            {
                "turnIndex": i,
                "userMessage": turn.user_message,
                "assembledResponse": result.assembled_response if result else None,
                "overallVerdict": raw_verdict.lower() if raw_verdict else None,
                "errorStatus": "failed" if is_error else None,
                "errorStage": result.error_stage if result else None,
                "parameters": params,
            }
        )

    return filename, json.dumps(result_array, indent=2, ensure_ascii=False)
