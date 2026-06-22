"""Chat session routes: wizard, session list, chat interface, SSE endpoint, export (017)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse

from harness.auth.middleware import require_auth
from harness.chat import event_bus as bus_registry
from harness.chat.session_service import ChatSessionService
from harness.chat.stream_orchestrator import run_turn
from harness.chat.turn_service import TurnService
from harness.persistence import get_session
from harness.persistence.models.connector_registration import ConnectorRegistration
from harness.persistence.models.evaluator_registration import EvaluationAgentRegistration
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.ui._context import ctx
from harness.ui._templates import templates
from harness.ui.chat_session import view as session_view

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers

def _owner_oid(user: dict) -> str | None:
    return user.get("oid") if user else None


def _is_admin(user: dict) -> bool:
    return (user.get("role") == "admin") if user else True


def _require_session(repo: ChatSessionRepository, session_id: str, user: dict):
    """Return session; enforce owner scope (admins bypass)."""
    admin = _is_admin(user)
    oid = _owner_oid(user)
    s = repo.get_session(session_id, owner_oid=None if admin else oid)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


# ---------------------------------------------------------------------------
# Wizard: 5-step session creation (T021)

@router.get("/chat/wizard/step1", name="wizard_step1")
def wizard_step1(request: Request, user: dict = Depends(require_auth)):
    request.session.pop("chat_wizard", None)
    return templates.TemplateResponse(
        request,
        "chat_session/wizard_step1.html",
        {"errors": {}, "form": {}, **ctx(request)},
    )


@router.post("/chat/wizard/step1", name="wizard_step1_post")
def wizard_step1_post(
    request: Request,
    session_name: str = Form(None),
    user: dict = Depends(require_auth),
):
    from harness.ui.chat_session.wizard_steps import validate_step1

    form = {"session_name": session_name or ""}
    errors = validate_step1(form)
    if errors:
        return templates.TemplateResponse(
            request,
            "chat_session/wizard_step1.html",
            {"errors": errors, "form": form, **ctx(request)},
            status_code=400,
        )
    wizard = request.session.get("chat_wizard", {})
    wizard["session_name"] = (session_name or "").strip()
    request.session["chat_wizard"] = wizard
    return RedirectResponse(request.url_for("wizard_step2"), status_code=303)


@router.get("/chat/wizard/step2", name="wizard_step2")
def wizard_step2(request: Request, user: dict = Depends(require_auth)):
    with get_session() as db:
        from sqlalchemy import select
        connectors = list(
            db.scalars(
                select(ConnectorRegistration).where(
                    ConnectorRegistration.supports_sse.is_(True),
                    ConnectorRegistration.archived.is_(False),
                )
            )
        )
    wizard = request.session.get("chat_wizard", {})
    return templates.TemplateResponse(
        request,
        "chat_session/wizard_step2.html",
        {
            "errors": {},
            "form": {"connector_id": wizard.get("connector_id", "")},
            "connectors": connectors,
            **ctx(request),
        },
    )


@router.post("/chat/wizard/step2", name="wizard_step2_post")
def wizard_step2_post(
    request: Request,
    connector_id: str = Form(None),
    user: dict = Depends(require_auth),
):
    from harness.ui.chat_session.wizard_steps import validate_step2
    from sqlalchemy import select

    cid = (connector_id or "").strip()
    form = {"connector_id": cid}
    with get_session() as db:
        connector = db.get(ConnectorRegistration, cid) if cid else None
        connectors = list(
            db.scalars(
                select(ConnectorRegistration).where(
                    ConnectorRegistration.supports_sse.is_(True),
                    ConnectorRegistration.archived.is_(False),
                )
            )
        )
        errors = validate_step2(form, connector)
        if errors:
            return templates.TemplateResponse(
                request,
                "chat_session/wizard_step2.html",
                {"errors": errors, "form": form, "connectors": connectors, **ctx(request)},
                status_code=400,
            )
        connector_name = connector.display_name
    wizard = request.session.get("chat_wizard", {})
    wizard["connector_id"] = cid
    wizard["connector_name"] = connector_name
    request.session["chat_wizard"] = wizard
    return RedirectResponse(request.url_for("wizard_step3"), status_code=303)


@router.get("/chat/wizard/step3", name="wizard_step3")
def wizard_step3(request: Request, user: dict = Depends(require_auth)):
    return templates.TemplateResponse(
        request,
        "chat_session/wizard_step3.html",
        {"errors": {}, "form": {}, **ctx(request)},
    )


@router.post("/chat/wizard/step3", name="wizard_step3_post")
def wizard_step3_post(
    request: Request,
    test_id: str = Form(None),
    password: str = Form(None),
    user: dict = Depends(require_auth),
):
    from harness.ui.chat_session.wizard_steps import validate_step3

    form = {"test_id": test_id or "", "password": password or ""}
    errors = validate_step3(form)
    if errors:
        return templates.TemplateResponse(
            request,
            "chat_session/wizard_step3.html",
            {"errors": errors, "form": {"test_id": form["test_id"]}, **ctx(request)},
            status_code=400,
        )
    wizard = request.session.get("chat_wizard", {})
    wizard["test_id"] = (test_id or "").strip()
    wizard["password"] = password or ""
    request.session["chat_wizard"] = wizard
    return RedirectResponse(request.url_for("wizard_step4"), status_code=303)


@router.get("/chat/wizard/step4", name="wizard_step4")
def wizard_step4(request: Request, user: dict = Depends(require_auth)):
    with get_session() as db:
        from sqlalchemy import select
        evaluators = list(
            db.scalars(
                select(EvaluationAgentRegistration).where(
                    EvaluationAgentRegistration.supports_sse.is_(True),
                    EvaluationAgentRegistration.archived.is_(False),
                )
            )
        )
    wizard = request.session.get("chat_wizard", {})
    return templates.TemplateResponse(
        request,
        "chat_session/wizard_step4.html",
        {
            "errors": {},
            "form": {"evaluator_id": wizard.get("evaluator_id", "")},
            "evaluators": evaluators,
            **ctx(request),
        },
    )


@router.post("/chat/wizard/step4", name="wizard_step4_post")
def wizard_step4_post(
    request: Request,
    evaluator_id: str = Form(None),
    user: dict = Depends(require_auth),
):
    from harness.ui.chat_session.wizard_steps import validate_step4
    from sqlalchemy import select

    eid = (evaluator_id or "").strip()
    form = {"evaluator_id": eid}
    with get_session() as db:
        evaluator = db.get(EvaluationAgentRegistration, eid) if eid else None
        evaluators = list(
            db.scalars(
                select(EvaluationAgentRegistration).where(
                    EvaluationAgentRegistration.supports_sse.is_(True),
                    EvaluationAgentRegistration.archived.is_(False),
                )
            )
        )
        errors = validate_step4(form, evaluator)
        if errors:
            return templates.TemplateResponse(
                request,
                "chat_session/wizard_step4.html",
                {"errors": errors, "form": form, "evaluators": evaluators, **ctx(request)},
                status_code=400,
            )
        evaluator_name = evaluator.display_name
    wizard = request.session.get("chat_wizard", {})
    wizard["evaluator_id"] = eid
    wizard["evaluator_name"] = evaluator_name
    request.session["chat_wizard"] = wizard
    return RedirectResponse(request.url_for("wizard_step5"), status_code=303)


@router.get("/chat/wizard/step5", name="wizard_step5")
def wizard_step5(request: Request, user: dict = Depends(require_auth)):
    from harness.ui.chat_session.wizard_steps import validate_step5

    wizard = request.session.get("chat_wizard", {})
    errors = validate_step5(wizard)
    return templates.TemplateResponse(
        request,
        "chat_session/wizard_step5.html",
        {"errors": errors, "wizard": wizard, **ctx(request)},
    )


@router.post("/chat/wizard/step5", name="wizard_step5_post")
def wizard_step5_post(request: Request, user: dict = Depends(require_auth)):
    from harness.ui.chat_session.wizard_steps import validate_step5

    wizard = request.session.get("chat_wizard", {})
    errors = validate_step5(wizard)
    if errors:
        return templates.TemplateResponse(
            request,
            "chat_session/wizard_step5.html",
            {"errors": errors, "wizard": wizard, **ctx(request)},
            status_code=400,
        )
    oid = _owner_oid(user) or "anonymous"
    with get_session() as db:
        service = ChatSessionService(db)
        chat_session = service.create_session(
            name=wizard["session_name"],
            connector_id=wizard["connector_id"],
            test_id=wizard["test_id"],
            password=wizard["password"],
            evaluator_id=wizard["evaluator_id"],
            owner_oid=oid,
        )
        session_id = chat_session.chat_session_id
    request.session.pop("chat_wizard", None)
    return RedirectResponse(
        request.url_for("chat_interface", session_id=session_id), status_code=303
    )


# ---------------------------------------------------------------------------
# Session list (T025)

@router.get("/chat/sessions", name="chat_session_list")
def chat_session_list(
    request: Request,
    sort: str = Query("created_at"),
    dir: str = Query("desc"),
    user: dict = Depends(require_auth),
):
    admin = _is_admin(user)
    oid = _owner_oid(user)
    with get_session() as db:
        repo = ChatSessionRepository(db)
        sessions = repo.list_all_sessions() if admin else repo.list_sessions_for_owner(oid or "")
        turn_counts = repo.get_turn_counts([s.chat_session_id for s in sessions])
        rows = [session_view.session_row_view(s, turn_counts[s.chat_session_id]) for s in sessions]
    rows = session_view.sort_sessions(rows, sort, dir)
    return templates.TemplateResponse(
        request,
        "chat_session/list.html",
        {"sessions": rows, "sort": sort, "dir": dir, "is_admin": admin, **ctx(request)},
    )


# ---------------------------------------------------------------------------
# Chat interface (T034)

@router.get("/chat/sessions/{session_id}", name="chat_interface")
def chat_interface(
    request: Request,
    session_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = _require_session(repo, session_id, user)
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from harness.persistence.models.chat_turn import ChatTurn
        turns = list(
            db.scalars(
                select(ChatTurn)
                .where(ChatTurn.session_id == session_id)
                .order_by(ChatTurn.created_at.desc())
                .limit(50)
                .options(
                    selectinload(ChatTurn.result),
                    selectinload(ChatTurn.evaluation_events),
                )
            )
        )
        turns = list(reversed(turns))
        turn_views = [session_view.turn_view(t) for t in turns]
        eval_turns = [
            {"turnIndex": idx, "events": tv["evaluation_events"], "finalResult": tv["final_evaluation_result"]}
            for idx, tv in enumerate(turn_views, start=1)
            if tv["evaluation_events"] or tv["final_evaluation_result"]
        ]
        eval_turns_json = json.dumps(eval_turns)
        turn_count = len(turn_views)
        from harness.persistence.encryption import decrypt_credential
        try:
            test_id = decrypt_credential(chat_session.test_id_enc)
        except Exception:
            test_id = ""
    return templates.TemplateResponse(
        request,
        "chat_session/interface.html",
        {
            "chat_session": chat_session,
            "turns": turn_views,
            "eval_turns_json": eval_turns_json,
            "turn_count": turn_count,
            "test_id": test_id,
            "is_owner": not _is_admin(user) or _owner_oid(user) == chat_session.owner_oid,
            **ctx(request),
        },
    )


# ---------------------------------------------------------------------------
# Turn submission (T032)

@router.post("/chat/sessions/{session_id}/turns", name="chat_submit_turn")
async def chat_submit_turn(
    request: Request,
    session_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_auth),
):
    body = await request.json()
    user_message = (body.get("message") or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    with get_session() as db:
        repo = ChatSessionRepository(db)
        _require_session(repo, session_id, user)
        turn_svc = TurnService(db)
        turn = turn_svc.create_turn(session_id, user_message)
        turn_id = turn.turn_id

    bus = bus_registry.create_bus(turn_id)
    background_tasks.add_task(run_turn, turn_id, session_id, user_message, bus)
    return {"turn_id": turn_id}


# ---------------------------------------------------------------------------
# Per-turn SSE stream (T033)

@router.get("/chat/sessions/{session_id}/turns/{turn_id}/stream", name="chat_turn_stream")
async def chat_turn_stream(
    request: Request,
    session_id: str,
    turn_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as db:
        repo = ChatSessionRepository(db)
        _require_session(repo, session_id, user)
        turn = repo.get_turn(turn_id, session_id)
        if turn is None:
            raise HTTPException(status_code=404, detail="Turn not found")

        turn_status = turn.status

        # For completed/failed turns, replay persisted events from DB
        if turn_status in ("completed", "failed"):
            events_from_db = []
            result = turn.result
            ev_rows = turn.evaluation_events or []
            if turn_status == "completed" and result:
                if result.assembled_response:
                    events_from_db.append(
                        {"event": "connector_token", "data": {"content": result.assembled_response}}
                    )
                events_from_db.append({"event": "evaluating", "data": {}})
                for ev in ev_rows:
                    events_from_db.append(
                        {"event": "evaluator_event", "data": {"event_type": ev.event_type, "payload": ev.payload}}
                    )
                events_from_db.append(
                    {"event": "turn_complete", "data": {"turn_id": turn_id, "assembled_response": result.assembled_response or ""}}
                )
            else:
                if result:
                    events_from_db.append(
                        {
                            "event": "turn_failed",
                            "data": {
                                "turn_id": turn_id,
                                "error_stage": result.error_stage or "unknown",
                                "error_details": result.error_details or "",
                            },
                        }
                    )

            async def replay_stream():
                for ev in events_from_db:
                    yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'])}\n\n"

            return StreamingResponse(replay_stream(), media_type="text/event-stream")

    # in_progress: stream from live bus
    bus = bus_registry.get_bus(turn_id)

    async def live_stream():
        if bus is None:
            yield f"event: turn_failed\ndata: {json.dumps({'turn_id': turn_id, 'error_stage': 'server_restart', 'error_details': 'Stream bus not found'})}\n\n"
            return
        async for event in bus.stream_from(cursor=0):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            if event["event"] in ("turn_complete", "turn_failed"):
                break

    return StreamingResponse(live_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Export (T037)

@router.get("/chat/sessions/{session_id}/export", name="chat_session_export")
def chat_session_export(
    request: Request,
    session_id: str,
    format: str = Query("json"),
    user: dict = Depends(require_auth),
):
    from harness.chat.export_service import build_session_export

    fmt = format.lower()
    if fmt not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'csv'")

    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = _require_session(repo, session_id, user)
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from harness.persistence.models.chat_turn import ChatTurn
        turns = list(
            db.scalars(
                select(ChatTurn)
                .where(ChatTurn.session_id == session_id)
                .order_by(ChatTurn.created_at)
                .options(
                    selectinload(ChatTurn.result),
                    selectinload(ChatTurn.evaluation_events),
                )
            )
        )
        filename, mimetype, content_bytes = build_session_export(chat_session, turns, fmt)
    return StreamingResponse(
        iter([content_bytes]),
        media_type=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Bulk clear (T045)

@router.post("/chat/sessions/clear-errors", name="chat_clear_errors")
def chat_clear_errors(request: Request, user: dict = Depends(require_auth)):
    """Delete all sessions with at least one failed turn (owner-scoped for users, global for admins)."""
    admin = _is_admin(user)
    oid = _owner_oid(user)
    with get_session() as db:
        repo = ChatSessionRepository(db)
        repo.delete_errored_sessions(owner_oid=None if admin else oid)
    return RedirectResponse(request.url_for("chat_session_list"), status_code=303)


@router.post("/chat/sessions/clear-all", name="chat_clear_all")
def chat_clear_all(request: Request, user: dict = Depends(require_auth)):
    """Delete all inactive sessions (owner-scoped for users, global for admins)."""
    admin = _is_admin(user)
    oid = _owner_oid(user)
    with get_session() as db:
        repo = ChatSessionRepository(db)
        repo.delete_all_inactive_sessions(owner_oid=None if admin else oid)
    return RedirectResponse(request.url_for("chat_session_list"), status_code=303)


# ---------------------------------------------------------------------------
# Tester delete (T039)

@router.post("/chat/sessions/{session_id}/delete", name="chat_session_delete")
def chat_session_delete(
    request: Request,
    session_id: str,
    confirm: str = Query(""),
    user: dict = Depends(require_auth),
):
    admin = _is_admin(user)
    oid = _owner_oid(user)
    stale_turn_id = None
    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = repo.get_session(session_id, owner_oid=None if admin else oid)
        if chat_session is None:
            raise HTTPException(status_code=404)
        in_progress = repo.get_in_progress_turn(session_id)
        if in_progress is not None and confirm.lower() != "true":
            # Redirect back to session list with warning (confirmed via query param)
            return RedirectResponse(
                str(request.url_for("chat_session_list"))
                + f"?warn_in_progress={session_id}",
                status_code=303,
            )
        if in_progress is not None:
            stale_turn_id = in_progress.turn_id
        repo.delete_session(session_id)
    if stale_turn_id:
        bus_registry.remove_bus(stale_turn_id)
    return RedirectResponse(request.url_for("chat_session_list"), status_code=303)


# ---------------------------------------------------------------------------
# Admin delete (T044)

@router.post("/chat/sessions/{session_id}/admin-delete", name="chat_session_admin_delete")
def chat_session_admin_delete(
    request: Request,
    session_id: str,
    user: dict = Depends(require_auth),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin role required")
    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = repo.get_session(session_id)
        if chat_session is None:
            raise HTTPException(status_code=404)
        in_progress = repo.get_in_progress_turn(session_id)
        if in_progress is not None:
            # Silently skip — do not delete sessions with active turns.
            # No remove_bus needed: nothing is deleted, so no bus cleanup is required.
            return RedirectResponse(request.url_for("chat_session_list"), status_code=303)
        repo.delete_session(session_id)
    # No in-progress turn existed (guard above prevents reaching here otherwise),
    # so no live bus entry to clean up.
    return RedirectResponse(request.url_for("chat_session_list"), status_code=303)
