"""Evaluator Registry management routes (014). Mirrors the connector registry router."""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from harness.auth.middleware import require_auth, require_role
from harness.evaluator_registry import (
    EvaluatorRegistryService,
    RegistrationInUseError,
    parse_evaluator_form,
    run_test_connection,
)
from harness.evaluator_registry.forms import parse_dimensions
from harness.evaluator_registry.test_connection import TestConnectionResult
from harness.persistence import get_session
from harness.ui._context import ctx
from harness.ui._registry_forms import descriptor_from_form as _descriptor_from_form
from harness.ui._templates import templates

router = APIRouter()

_TRUTHY = {"1", "true", "on", "yes"}
_PREVIEW = 3


def _reg_to_view(reg) -> dict:
    """Non-secret projection — credential/password are NEVER included (SC-002)."""
    descriptor = reg.auth_descriptor or {}
    dims = list(reg.declared_scoring_dimensions or [])
    preview = ", ".join(dims[:_PREVIEW])
    if len(dims) > _PREVIEW:
        preview += f", + {len(dims) - _PREVIEW} more"
    return {
        "evaluation_agent_id": reg.evaluation_agent_id,
        "display_name": reg.display_name,
        "description": reg.description,
        "endpoint_url": reg.endpoint_url,
        "auth_mode": descriptor.get("mode"),
        "header_name": descriptor.get("headerName"),
        "username": descriptor.get("username"),
        "token_url": descriptor.get("tokenUrl"),
        "client_id": descriptor.get("clientId"),
        "scope": descriptor.get("scope"),
        "audience": descriptor.get("audience"),
        "timeout_seconds": reg.timeout_seconds,
        "declared_scoring_dimensions": dims,
        "dimensions_text": "\n".join(dims),
        "dimensions_preview": preview,
        "supports_sse": reg.supports_sse,
        "score_scale_min": reg.score_scale_min,
        "score_scale_max": reg.score_scale_max,
        "scoring_thresholds": reg.scoring_thresholds,
        "scoring_thresholds_json": (
            _json.dumps(reg.scoring_thresholds, indent=2) if reg.scoring_thresholds else ""
        ),
        "archived": reg.archived,
        "updated_at": reg.updated_at,
    }


@router.get("/evaluators")
def list_evaluators(
    request: Request,
    filter: str = Query("active"),
    q: str = Query(""),
    user: dict = Depends(require_auth),
):
    filter_ = filter
    q_val = q or None
    with get_session() as session:
        regs = EvaluatorRegistryService(session).list_registrations(filter=filter_, q=q_val)
        views = [_reg_to_view(r) for r in regs]
    return templates.TemplateResponse(
        request,
        "evaluator_registry/list.html",
        {
            "registrations": views,
            "filter": filter_,
            "q": q or "",
            "error": None,
            **ctx(request),
        },
    )


@router.get("/evaluators/new")
def new_evaluator(
    request: Request,
    next: str = Query(""),
    user: dict = Depends(require_auth),
):
    return templates.TemplateResponse(
        request,
        "evaluator_registry/form.html",
        {
            "mode_label": "Register new evaluator",
            "reg": None,
            "errors": {},
            "form": {},
            "next_url": next,
            **ctx(request),
        },
    )


@router.get("/evaluators/{evaluation_agent_id}", name="view_evaluator")
def view_evaluator(
    request: Request,
    evaluation_agent_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        reg = EvaluatorRegistryService(session).get(evaluation_agent_id)
        if reg is None:
            raise HTTPException(status_code=404)
        reg_view = _reg_to_view(reg)
    return templates.TemplateResponse(
        request,
        "evaluator_registry/detail.html",
        {"reg": reg_view, **ctx(request)},
    )


@router.post("/evaluators")
def create_evaluator(
    request: Request,
    display_name: str = Form(None),
    description: str = Form(None),
    endpoint_url: str = Form(None),
    auth_mode: str = Form(None),
    token: str = Form(None),
    header_name: str = Form(None),
    header_value: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    token_url: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    scope: str = Form(None),
    audience: str = Form(None),
    timeout_seconds: str = Form(None),
    dimensions: str = Form(None),
    supports_sse: str = Form(None),
    score_scale_min: str = Form(None),
    score_scale_max: str = Form(None),
    scoring_thresholds_json: str = Form(None),
    replace_credential: str = Form(None),
    next_url: str = Form(None, alias="next"),
    evaluation_agent_id: str = Form(None),
    user: dict = Depends(require_auth),
):
    form = {k: v for k, v in {
        "display_name": display_name, "description": description,
        "endpoint_url": endpoint_url, "auth_mode": auth_mode, "token": token,
        "header_name": header_name, "header_value": header_value,
        "username": username, "password": password, "token_url": token_url,
        "client_id": client_id, "client_secret": client_secret,
        "scope": scope, "audience": audience, "timeout_seconds": timeout_seconds,
        "dimensions": dimensions, "supports_sse": supports_sse,
        "score_scale_min": score_scale_min, "score_scale_max": score_scale_max,
        "scoring_thresholds_json": scoring_thresholds_json,
        "replace_credential": replace_credential,
        "next": next_url, "evaluation_agent_id": evaluation_agent_id,
    }.items() if v is not None}
    next_redirect = next_url or ""
    payload, errors = parse_evaluator_form(form, require_credential=True)
    if errors:
        return templates.TemplateResponse(
            request,
            "evaluator_registry/form.html",
            {
                "mode_label": "Register new evaluator",
                "reg": None,
                "errors": errors,
                "form": form,
                "next_url": next_redirect,
                **ctx(request),
            },
            status_code=400,
        )
    with get_session() as session:
        EvaluatorRegistryService(session).create(payload)
    if next_redirect == "dashboard":
        return RedirectResponse(request.url_for("index"), status_code=303)
    return RedirectResponse(request.url_for("list_evaluators"), status_code=303)


@router.post("/evaluators/test-connection")
def test_connection_evaluator(
    request: Request,
    endpoint_url: str = Form(None),
    auth_mode: str = Form(None),
    token: str = Form(None),
    header_name: str = Form(None),
    header_value: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    token_url: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    scope: str = Form(None),
    audience: str = Form(None),
    timeout_seconds: str = Form(None),
    dimensions: str = Form(None),
    supports_sse: str = Form(None),
    evaluation_agent_id: str = Form(None),
    user: dict = Depends(require_role("admin")),
):
    form = {k: v for k, v in {
        "endpoint_url": endpoint_url, "auth_mode": auth_mode, "token": token,
        "header_name": header_name, "header_value": header_value,
        "username": username, "password": password, "token_url": token_url,
        "client_id": client_id, "client_secret": client_secret,
        "scope": scope, "audience": audience, "timeout_seconds": timeout_seconds,
        "dimensions": dimensions, "supports_sse": supports_sse,
        "evaluation_agent_id": evaluation_agent_id,
    }.items() if v is not None}
    endpoint = (form.get("endpoint_url") or "").strip()
    mode = (form.get("auth_mode") or "none").strip()
    try:
        timeout = int(form.get("timeout_seconds") or 60)
    except ValueError:
        timeout = 60
    dims_val = parse_dimensions(form.get("dimensions"))
    sse = (form.get("supports_sse") or "").lower() in _TRUTHY
    eid = (form.get("evaluation_agent_id") or "").strip()

    descriptor, needs_stored = _descriptor_from_form(form, mode)
    if needs_stored and eid:
        with get_session() as session:
            descriptor = EvaluatorRegistryService(session).get_auth_descriptor_decrypted(eid)

    result = run_test_connection(endpoint, descriptor, timeout, dims_val, sse)
    return templates.TemplateResponse(
        request, "evaluator_registry/_test_result.html", {"result": result}
    )


@router.post("/evaluators/{evaluation_agent_id}/test", name="test_evaluator_by_id")
def test_evaluator_by_id(
    request: Request,
    evaluation_agent_id: str,
    user: dict = Depends(require_auth),
):
    """Test a registered evaluator by ID, using its stored (decrypted) credentials."""
    with get_session() as session:
        service = EvaluatorRegistryService(session)
        reg = service.get(evaluation_agent_id)
        if reg is None:
            result = TestConnectionResult(False, "not_found", None, "Evaluator not found.")
            return templates.TemplateResponse(
                request, "evaluator_registry/_test_result.html", {"result": result}
            )
        descriptor = service.get_auth_descriptor_decrypted(evaluation_agent_id)
        endpoint = reg.endpoint_url
        timeout = reg.timeout_seconds
        dims = list(reg.declared_scoring_dimensions or [])
        sse = reg.supports_sse
    result = run_test_connection(endpoint, descriptor, timeout, dims, sse)
    return templates.TemplateResponse(
        request, "evaluator_registry/_test_result.html", {"result": result}
    )


@router.get("/evaluators/{evaluation_agent_id}/edit")
def edit_evaluator(
    request: Request,
    evaluation_agent_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        reg = EvaluatorRegistryService(session).get(evaluation_agent_id)
        if reg is None:
            raise HTTPException(status_code=404)
        reg_view = _reg_to_view(reg)
    return templates.TemplateResponse(
        request,
        "evaluator_registry/form.html",
        {
            "mode_label": "Edit evaluator",
            "reg": reg_view,
            "errors": {},
            "form": {},
            "next_url": "",
            **ctx(request),
        },
    )


@router.post("/evaluators/{evaluation_agent_id}")
def update_evaluator(
    request: Request,
    evaluation_agent_id: str,
    display_name: str = Form(None),
    description: str = Form(None),
    endpoint_url: str = Form(None),
    auth_mode: str = Form(None),
    token: str = Form(None),
    header_name: str = Form(None),
    header_value: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    token_url: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    scope: str = Form(None),
    audience: str = Form(None),
    timeout_seconds: str = Form(None),
    dimensions: str = Form(None),
    supports_sse: str = Form(None),
    score_scale_min: str = Form(None),
    score_scale_max: str = Form(None),
    scoring_thresholds_json: str = Form(None),
    replace_credential: str = Form(None),
    user: dict = Depends(require_auth),
):
    form = {k: v for k, v in {
        "display_name": display_name, "description": description,
        "endpoint_url": endpoint_url, "auth_mode": auth_mode, "token": token,
        "header_name": header_name, "header_value": header_value,
        "username": username, "password": password, "token_url": token_url,
        "client_id": client_id, "client_secret": client_secret,
        "scope": scope, "audience": audience, "timeout_seconds": timeout_seconds,
        "dimensions": dimensions, "supports_sse": supports_sse,
        "score_scale_min": score_scale_min, "score_scale_max": score_scale_max,
        "scoring_thresholds_json": scoring_thresholds_json,
        "replace_credential": replace_credential,
    }.items() if v is not None}
    replace = (form.get("replace_credential") or "").lower() in _TRUTHY
    with get_session() as session:
        service = EvaluatorRegistryService(session)
        existing = service.get(evaluation_agent_id)
        if existing is None:
            raise HTTPException(status_code=404)
        stored_mode = (existing.auth_descriptor or {}).get("mode")
        new_mode = (form.get("auth_mode") or "").strip()
        require_cred = replace or (new_mode != stored_mode)
        payload, errors = parse_evaluator_form(form, require_credential=require_cred)
        if errors:
            reg_view = _reg_to_view(existing)
            return templates.TemplateResponse(
                request,
                "evaluator_registry/form.html",
                {
                    "mode_label": "Edit evaluator",
                    "reg": reg_view,
                    "errors": errors,
                    "form": form,
                    "next_url": "",
                    **ctx(request),
                },
                status_code=400,
            )
        service.update(evaluation_agent_id, payload, replace_credential=require_cred)
    return RedirectResponse(request.url_for("list_evaluators"), status_code=303)


@router.post("/evaluators/{evaluation_agent_id}/archive")
def archive_evaluator(
    request: Request,
    evaluation_agent_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        EvaluatorRegistryService(session).archive(evaluation_agent_id)
    return RedirectResponse(request.url_for("list_evaluators"), status_code=303)


@router.post("/evaluators/{evaluation_agent_id}/restore")
def restore_evaluator(
    request: Request,
    evaluation_agent_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        EvaluatorRegistryService(session).restore(evaluation_agent_id)
    return RedirectResponse(request.url_for("list_evaluators"), status_code=303)


@router.post("/evaluators/{evaluation_agent_id}/delete")
def delete_evaluator(
    request: Request,
    evaluation_agent_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        service = EvaluatorRegistryService(session)
        try:
            service.hard_delete(evaluation_agent_id)
        except RegistrationInUseError as exc:
            views = [_reg_to_view(r) for r in service.list_registrations(filter="all")]
            return templates.TemplateResponse(
                request,
                "evaluator_registry/list.html",
                {
                    "registrations": views,
                    "filter": "all",
                    "q": "",
                    "error": str(exc),
                    **ctx(request),
                },
                status_code=409,
            )
    return RedirectResponse(request.url_for("list_evaluators"), status_code=303)


