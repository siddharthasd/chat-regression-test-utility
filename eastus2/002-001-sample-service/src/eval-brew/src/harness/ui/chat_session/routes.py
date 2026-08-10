"""Chat session routes: wizard, session list, chat interface, SSE endpoint, export (017, 019)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse

from harness.auth.middleware import require_auth
from harness.chat import event_bus as bus_registry
from harness.chat.session_service import ChatSessionService
from harness.chat.stream_orchestrator import run_turn
from harness.chat.turn_service import TurnService
from harness.connector_registry import ConnectorRegistryService as _ConnRegService
from harness.connector_registry import run_test_connection as _run_conn_test
from harness.evaluator_registry import EvaluatorRegistryService as _EvalRegService
from harness.evaluator_registry import run_test_connection as _run_eval_test
from harness.persistence import get_session
from harness.persistence.exceptions import HarnessKeyMismatchError
from harness.persistence.models.connector_registration import ConnectorRegistration
from harness.persistence.models.evaluator_registration import EvaluationAgentRegistration
from harness.persistence.repositories.chat_session_repository import ChatSessionRepository
from harness.ui._context import ctx
from harness.ui._templates import templates
from harness.ui.chat_session import view as session_view

# Seconds between SSE keep-alive comments sent while waiting for bus events.
# Prevents proxies (nginx, IIS ARR, Azure App Gateway) from closing idle connections.
_SSE_KEEPALIVE_INTERVAL = 15

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


def _require_owner_session(repo: ChatSessionRepository, session_id: str, user: dict):
    """Return session for analytics; always owner-scoped in production.

    When auth is disabled (local/test mode) there is no real OID, so falls back
    to the admin bypass — consistent with single-user dev behaviour.
    """
    from harness.auth.config import is_auth_enabled

    if not is_auth_enabled():
        s = repo.get_session(session_id, owner_oid=None)
    else:
        oid = _owner_oid(user)
        if not oid:
            raise HTTPException(status_code=403, detail="Access denied")
        s = repo.get_session(session_id, owner_oid=oid)
    if s is None:
        raise HTTPException(status_code=403, detail="Access denied")
    return s


TOOLTIP_COPY_CHAT = {
    "Mean": (
        "The average score for this parameter across all turns. "
        "Your baseline answer to \"how well did the chatbot perform on this dimension?\""
    ),
    "Median": (
        "The middle score when all turns are ranked from lowest to highest. "
        "If the median is noticeably lower than the mean, a small number of high-scoring "
        "turns are inflating the average. If the median is higher than the mean, a few "
        "poor turns are dragging it down. Mean and median close together means the scores "
        "are consistently spread."
    ),
    "Min": (
        "The lowest score any single turn received on this parameter. "
        "Represents the worst-case performance observed in this session."
    ),
    "Max": (
        "The highest score any single turn received on this parameter. "
        "Represents the best-case performance observed in this session."
    ),
    "Range": (
        "The gap between the best and worst scores (Max minus Min). A large range means "
        "performance was inconsistent. Some turns scored well, others did not. "
        "A small range means the chatbot performed at a similar level across all turns."
    ),
    "σ": (
        "Measures how spread out the scores are around the average. A low σ means most "
        "turns scored close to the mean. Predictable, consistent behaviour. A high σ "
        "means scores varied widely. Some turns were much better or worse than average. "
        "When comparing two parameters with the same mean, the one with the lower σ is more reliable."
    ),
    "Overall Mean Score": (
        "The average quality score across every turn and every evaluation parameter in this session. "
        "Think of it as the overall grade for the chatbot. Closer to the evaluator's maximum is better."
    ),
    "Overall Verdict Distribution": (
        "How the evaluator classified each turn overall. For example, how many Passed, "
        "how many triggered a Warning, how many Failed. A quick summary of the session's quality at a glance."
    ),
}


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
            "test_result": None,
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
                {"errors": errors, "form": form, "connectors": connectors, "test_result": None, **ctx(request)},
                status_code=400,
            )
        connector_name = connector.display_name
        endpoint = connector.endpoint_url
        timeout = connector.timeout_seconds
        expects = connector.expects_per_row_password
        sse = connector.supports_sse
        try:
            descriptor = _ConnRegService(db).get_auth_descriptor_decrypted(cid)
        except HarnessKeyMismatchError:
            return templates.TemplateResponse(
                request,
                "chat_session/wizard_step2.html",
                {
                    "errors": {"connector_id": "Could not decrypt connector credentials. Contact your administrator."},
                    "form": form,
                    "connectors": connectors,
                    "test_result": None,
                    **ctx(request),
                },
                status_code=400,
            )

    test_result = _run_conn_test(endpoint, descriptor, timeout, expects, sse)
    if not test_result.ok:
        return templates.TemplateResponse(
            request,
            "chat_session/wizard_step2.html",
            {
                "errors": {"connector_id": f"Connection test failed: {test_result.detail}"},
                "form": form,
                "connectors": connectors,
                "test_result": test_result,
                **ctx(request),
            },
            status_code=400,
        )

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
    from harness.persistence.encryption import encrypt_credential
    wizard = request.session.get("chat_wizard", {})
    wizard["test_id"] = (test_id or "").strip()
    raw = password or ""
    wizard["password"] = encrypt_credential(raw) if raw else ""
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
            "test_result": None,
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
                {"errors": errors, "form": form, "evaluators": evaluators, "test_result": None, **ctx(request)},
                status_code=400,
            )
        evaluator_name = evaluator.display_name
        endpoint = evaluator.endpoint_url
        timeout = evaluator.timeout_seconds
        dims = list(evaluator.declared_scoring_dimensions or [])
        sse = evaluator.supports_sse
        try:
            descriptor = _EvalRegService(db).get_auth_descriptor_decrypted(eid)
        except HarnessKeyMismatchError:
            return templates.TemplateResponse(
                request,
                "chat_session/wizard_step4.html",
                {
                    "errors": {"evaluator_id": "Could not decrypt evaluator credentials. Contact your administrator."},
                    "form": form,
                    "evaluators": evaluators,
                    "test_result": None,
                    **ctx(request),
                },
                status_code=400,
            )

    test_result = _run_eval_test(endpoint, descriptor, timeout, dims, sse)
    if not test_result.ok:
        return templates.TemplateResponse(
            request,
            "chat_session/wizard_step4.html",
            {
                "errors": {"evaluator_id": f"Evaluator test failed: {test_result.detail}"},
                "form": form,
                "evaluators": evaluators,
                "test_result": test_result,
                **ctx(request),
            },
            status_code=400,
        )

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
    from harness.persistence.encryption import decrypt_credential
    oid = _owner_oid(user) or "anonymous"
    enc_pw = wizard.get("password", "")
    plaintext_password = decrypt_credential(enc_pw) if enc_pw else ""
    with get_session() as db:
        service = ChatSessionService(db)
        chat_session = service.create_session(
            name=wizard["session_name"],
            connector_id=wizard["connector_id"],
            test_id=wizard["test_id"],
            password=plaintext_password,
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
            {
                "turnIndex": idx,
                "events": tv["evaluation_events"],
                "finalResult": tv["final_evaluation_result"],
                "connectorTokens": tv.get("connector_token_count"),
                "evaluatorTokens": tv.get("evaluator_token_count"),
                "totalTokens": tv.get("total_token_count"),
            }
            for idx, tv in enumerate(turn_views, start=1)
            if tv["evaluation_events"] or tv["final_evaluation_result"]
        ]
        turn_count = len(turn_views)
        session_total_tokens = sum(
            (tv.get("connector_token_count") or 0) + (tv.get("evaluator_token_count") or 0)
            for tv in turn_views
        )
        session_connector_tokens = sum(
            tv.get("connector_token_count") or 0 for tv in turn_views
        )
        session_evaluator_tokens = sum(
            tv.get("evaluator_token_count") or 0 for tv in turn_views
        )
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
            "eval_turns": eval_turns,
            "turn_count": turn_count,
            "session_total_tokens": session_total_tokens,
            "session_connector_tokens": session_connector_tokens,
            "session_evaluator_tokens": session_evaluator_tokens,
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

            return StreamingResponse(
                replay_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    # in_progress: stream from live bus
    bus = bus_registry.get_bus(turn_id)

    async def live_stream():
        if bus is None:
            yield f"event: turn_failed\ndata: {json.dumps({'turn_id': turn_id, 'error_stage': 'server_restart', 'error_details': 'Stream bus not found'})}\n\n"
            return

        # Drain bus events into a Queue so we can interleave keep-alive SSE comments
        # while waiting, preventing intermediate proxies from closing the idle connection.
        q: asyncio.Queue = asyncio.Queue()

        async def _drain() -> None:
            async for ev in bus.stream_from(cursor=0):
                await q.put(ev)
            await q.put(None)  # terminal sentinel

        drain_task = asyncio.create_task(_drain())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=_SSE_KEEPALIVE_INTERVAL)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if item is None:
                    break
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
                if item["event"] in ("turn_complete", "turn_failed"):
                    break
        finally:
            drain_task.cancel()
            try:
                await drain_task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        live_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
# Analytics (019)

@router.get("/chat/sessions/{session_id}/analytics", name="chat_session_analytics")
def chat_session_analytics(
    request: Request,
    session_id: str,
    q: str = Query(""),
    verdict: list[str] = Query(None),
    error_only: bool = Query(False),
    sort: str = Query("turn_index"),
    dir: str = Query("asc"),
    user: dict = Depends(require_auth),
):
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    from harness.persistence.models.chat_turn import ChatTurn
    from harness.ui.chat_session.view import _VERDICT_ORDER
    from harness.ui.detail.analytics import compute_analytics

    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = _require_owner_session(repo, session_id, user)

        total_turn_count = db.scalar(
            select(func.count(ChatTurn.turn_id)).where(
                ChatTurn.session_id == session_id
            )
        ) or 0

        turns = list(
            db.scalars(
                select(ChatTurn)
                .where(
                    ChatTurn.session_id == session_id,
                    ChatTurn.status.in_(["completed", "failed"]),
                )
                .order_by(ChatTurn.created_at)
                .options(selectinload(ChatTurn.result))
            )
        )

    declared_dims = chat_session.evaluator_declared_scoring_dimensions or []
    skip_analytics = total_turn_count > 5000
    failed_turn_count = sum(1 for t in turns if t.status == "failed")

    analytics = None
    analytics_empty = False
    if not skip_analytics:
        entries = session_view.score_entries_from_turns(turns)
        analytics = compute_analytics(
            entries, declared_dims,
            score_scale_min=chat_session.evaluator_score_scale_min,
            score_scale_max=chat_session.evaluator_score_scale_max,
        )
        analytics_empty = analytics.evaluated_count == 0

    all_rows = [
        session_view.turn_explorer_view(t, i, declared_dims)
        for i, t in enumerate(turns, start=1)
    ]

    filtered = list(all_rows)
    if verdict:
        filtered = [r for r in filtered if r["verdict"] in verdict]
    if error_only:
        filtered = [r for r in filtered if r["status"] == "failed"]
    if q.strip():
        needle = q.strip().lower()
        filtered = [
            r for r in filtered
            if needle in (r["user_message"] or "").lower()
            or needle in (r["assembled_response"] or "").lower()
        ]

    _sort_keys = {
        "turn_index": lambda r: r["turn_index"],
        "verdict": lambda r: _VERDICT_ORDER.get(r["verdict"] or "", 99),
    }
    key_fn = _sort_keys.get(sort, _sort_keys["turn_index"])
    filtered = sorted(filtered, key=key_fn, reverse=(dir == "desc"))

    return templates.TemplateResponse(
        request,
        "chat_session/analytics.html",
        {
            "chat_session": chat_session,
            "analytics": analytics,
            "analytics_empty": analytics_empty,
            "skip_analytics": skip_analytics,
            "total_turn_count": total_turn_count,
            "failed_turn_count": failed_turn_count,
            "rows": filtered,
            "total_rows": len(all_rows),
            "declared_dims": declared_dims,
            "q": q,
            "selected_verdicts": verdict or [],
            "error_only": error_only,
            "sort": sort,
            "dir": dir,
            "tooltip_copy": TOOLTIP_COPY_CHAT,
            **ctx(request),
        },
    )


@router.get("/chat/sessions/{session_id}/download-results.csv", name="chat_session_download_csv")
def chat_session_download_csv(
    request: Request,
    session_id: str,
    user: dict = Depends(require_auth),
):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from harness.persistence.models.chat_turn import ChatTurn

    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = _require_owner_session(repo, session_id, user)
        turns = list(
            db.scalars(
                select(ChatTurn)
                .where(
                    ChatTurn.session_id == session_id,
                    ChatTurn.status.in_(["completed", "failed"]),
                )
                .order_by(ChatTurn.created_at)
                .options(selectinload(ChatTurn.result))
            )
        )

    filename, csv_body = session_view.results_csv_builder(chat_session, turns)
    return Response(
        content=csv_body.encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/chat/sessions/{session_id}/download-results.json", name="chat_session_download_json")
def chat_session_download_json(
    request: Request,
    session_id: str,
    user: dict = Depends(require_auth),
):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from harness.persistence.models.chat_turn import ChatTurn

    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = _require_owner_session(repo, session_id, user)
        turns = list(
            db.scalars(
                select(ChatTurn)
                .where(
                    ChatTurn.session_id == session_id,
                    ChatTurn.status.in_(["completed", "failed"]),
                )
                .order_by(ChatTurn.created_at)
                .options(selectinload(ChatTurn.result))
            )
        )

    filename, json_body = session_view.results_json_builder(chat_session, turns)
    return Response(
        content=json_body.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    stale_turn_id = None
    with get_session() as db:
        repo = ChatSessionRepository(db)
        chat_session = repo.get_session(session_id)
        if chat_session is None:
            raise HTTPException(status_code=404)
        in_progress = repo.get_in_progress_turn(session_id)
        if in_progress is not None:
            stale_turn_id = in_progress.turn_id
        repo.delete_session(session_id)
    if stale_turn_id:
        bus_registry.remove_bus(stale_turn_id)
    return RedirectResponse(request.url_for("chat_session_list"), status_code=303)
