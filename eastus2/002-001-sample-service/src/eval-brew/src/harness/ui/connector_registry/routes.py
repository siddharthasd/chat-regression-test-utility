"""Connector Registry management routes (013). Server-rendered FastAPI router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from harness.auth.middleware import require_auth, require_role
from harness.connector_registry import (
    ConnectorRegistryService,
    RegistrationInUseError,
    parse_connector_form,
    run_test_connection,
)
from harness.connector_registry.test_connection import TestConnectionResult
from harness.persistence import get_session
from harness.ui._context import ctx
from harness.ui._registry_forms import descriptor_from_form as _descriptor_from_form
from harness.ui._templates import templates

router = APIRouter()

_TRUTHY = {"1", "true", "on", "yes"}


def _reg_to_view(reg) -> dict:
    """Non-secret projection for templates — credential/password are NEVER included (SC-002)."""
    descriptor = reg.auth_descriptor or {}
    return {
        "connector_id": reg.connector_id,
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
        "expects_per_row_password": reg.expects_per_row_password,
        "supports_sse": reg.supports_sse,
        "archived": reg.archived,
        "updated_at": reg.updated_at,
    }


@router.get("/connectors")
def list_connectors(
    request: Request,
    filter: str = Query("active"),
    q: str = Query(""),
    user: dict = Depends(require_auth),
):
    filter_ = filter
    q_val = q or None
    with get_session() as session:
        regs = ConnectorRegistryService(session).list_registrations(filter=filter_, q=q_val)
        views = [_reg_to_view(r) for r in regs]
    return templates.TemplateResponse(
        request,
        "connector_registry/list.html",
        {
            "registrations": views,
            "filter": filter_,
            "q": q or "",
            "error": None,
            **ctx(request),
        },
    )


@router.get("/connectors/new")
def new_connector(
    request: Request,
    next: str = Query(""),
    user: dict = Depends(require_auth),
):
    return templates.TemplateResponse(
        request,
        "connector_registry/form.html",
        {
            "mode_label": "Register new connector",
            "reg": None,
            "errors": {},
            "form": {},
            "next_url": next,
            **ctx(request),
        },
    )


@router.post("/connectors")
def create_connector(
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
    expects_per_row_password: str = Form(None),
    supports_sse: str = Form(None),
    replace_credential: str = Form(None),
    next_url: str = Form(None, alias="next"),
    connector_id: str = Form(None),
    user: dict = Depends(require_auth),
):
    form = {k: v for k, v in {
        "display_name": display_name, "description": description,
        "endpoint_url": endpoint_url, "auth_mode": auth_mode, "token": token,
        "header_name": header_name, "header_value": header_value,
        "username": username, "password": password, "token_url": token_url,
        "client_id": client_id, "client_secret": client_secret,
        "scope": scope, "audience": audience, "timeout_seconds": timeout_seconds,
        "expects_per_row_password": expects_per_row_password,
        "supports_sse": supports_sse,
        "replace_credential": replace_credential,
        "next": next_url, "connector_id": connector_id,
    }.items() if v is not None}
    next_redirect = next_url or ""
    payload, errors = parse_connector_form(form, require_credential=True)
    if errors:
        return templates.TemplateResponse(
            request,
            "connector_registry/form.html",
            {
                "mode_label": "Register new connector",
                "reg": None,
                "errors": errors,
                "form": form,
                "next_url": next_redirect,
                **ctx(request),
            },
            status_code=400,
        )
    with get_session() as session:
        ConnectorRegistryService(session).create(payload)
    if next_redirect == "dashboard":
        return RedirectResponse(request.url_for("index"), status_code=303)
    return RedirectResponse(request.url_for("list_connectors"), status_code=303)


@router.post("/connectors/test-connection")
def test_connection_connector(
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
    expects_per_row_password: str = Form(None),
    supports_sse: str = Form(None),
    connector_id: str = Form(None),
    user: dict = Depends(require_role("admin")),
):
    form = {k: v for k, v in {
        "endpoint_url": endpoint_url, "auth_mode": auth_mode, "token": token,
        "header_name": header_name, "header_value": header_value,
        "username": username, "password": password, "token_url": token_url,
        "client_id": client_id, "client_secret": client_secret,
        "scope": scope, "audience": audience, "timeout_seconds": timeout_seconds,
        "expects_per_row_password": expects_per_row_password,
        "supports_sse": supports_sse, "connector_id": connector_id,
    }.items() if v is not None}
    endpoint = (form.get("endpoint_url") or "").strip()
    mode = (form.get("auth_mode") or "none").strip()
    try:
        timeout = int(form.get("timeout_seconds") or 30)
    except ValueError:
        timeout = 30
    expects = (form.get("expects_per_row_password") or "").lower() in _TRUTHY
    sse = (form.get("supports_sse") or "").lower() in _TRUTHY
    cid = (form.get("connector_id") or "").strip()

    descriptor, needs_stored = _descriptor_from_form(form, mode)
    if needs_stored and cid:
        with get_session() as session:
            descriptor = ConnectorRegistryService(session).get_auth_descriptor_decrypted(cid)

    result = run_test_connection(endpoint, descriptor, timeout, expects, sse)
    return templates.TemplateResponse(
        request, "connector_registry/_test_result.html", {"result": result}
    )


@router.post("/connectors/{connector_id}/test", name="test_connector_by_id")
def test_connector_by_id(
    request: Request,
    connector_id: str,
    user: dict = Depends(require_auth),
):
    """Test a registered connector by ID, using its stored (decrypted) credentials."""
    with get_session() as session:
        service = ConnectorRegistryService(session)
        reg = service.get(connector_id)
        if reg is None:
            result = TestConnectionResult(False, "not_found", None, "Connector not found.")
            return templates.TemplateResponse(
                request, "connector_registry/_test_result.html", {"result": result}
            )
        descriptor = service.get_auth_descriptor_decrypted(connector_id)
        endpoint = reg.endpoint_url
        timeout = reg.timeout_seconds
        expects = reg.expects_per_row_password
        sse = reg.supports_sse
    result = run_test_connection(endpoint, descriptor, timeout, expects, sse)
    return templates.TemplateResponse(
        request, "connector_registry/_test_result.html", {"result": result}
    )


@router.get("/connectors/{connector_id}/edit")
def edit_connector(
    request: Request,
    connector_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        reg = ConnectorRegistryService(session).get(connector_id)
        if reg is None:
            raise HTTPException(status_code=404)
        reg_view = _reg_to_view(reg)
    return templates.TemplateResponse(
        request,
        "connector_registry/form.html",
        {
            "mode_label": "Edit connector",
            "reg": reg_view,
            "errors": {},
            "form": {},
            "next_url": "",
            **ctx(request),
        },
    )


@router.post("/connectors/{connector_id}")
def update_connector(
    request: Request,
    connector_id: str,
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
    expects_per_row_password: str = Form(None),
    supports_sse: str = Form(None),
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
        "expects_per_row_password": expects_per_row_password,
        "supports_sse": supports_sse,
        "replace_credential": replace_credential,
    }.items() if v is not None}
    replace = (form.get("replace_credential") or "").lower() in _TRUTHY
    with get_session() as session:
        service = ConnectorRegistryService(session)
        existing = service.get(connector_id)
        if existing is None:
            raise HTTPException(status_code=404)
        stored_mode = (existing.auth_descriptor or {}).get("mode")
        new_mode = (form.get("auth_mode") or "").strip()
        require_cred = replace or (new_mode != stored_mode)
        payload, errors = parse_connector_form(form, require_credential=require_cred)
        if errors:
            reg_view = _reg_to_view(existing)
            return templates.TemplateResponse(
                request,
                "connector_registry/form.html",
                {
                    "mode_label": "Edit connector",
                    "reg": reg_view,
                    "errors": errors,
                    "form": form,
                    "next_url": "",
                    **ctx(request),
                },
                status_code=400,
            )
        service.update(connector_id, payload, replace_credential=require_cred)
    return RedirectResponse(request.url_for("list_connectors"), status_code=303)


@router.post("/connectors/{connector_id}/archive")
def archive_connector(
    request: Request,
    connector_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        ConnectorRegistryService(session).archive(connector_id)
    return RedirectResponse(request.url_for("list_connectors"), status_code=303)


@router.post("/connectors/{connector_id}/restore")
def restore_connector(
    request: Request,
    connector_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        ConnectorRegistryService(session).restore(connector_id)
    return RedirectResponse(request.url_for("list_connectors"), status_code=303)


@router.post("/connectors/{connector_id}/delete")
def delete_connector(
    request: Request,
    connector_id: str,
    user: dict = Depends(require_auth),
):
    with get_session() as session:
        service = ConnectorRegistryService(session)
        try:
            service.hard_delete(connector_id)
        except RegistrationInUseError as exc:
            views = [_reg_to_view(r) for r in service.list_registrations(filter="all")]
            return templates.TemplateResponse(
                request,
                "connector_registry/list.html",
                {
                    "registrations": views,
                    "filter": "all",
                    "q": "",
                    "error": str(exc),
                    **ctx(request),
                },
                status_code=409,
            )
    return RedirectResponse(request.url_for("list_connectors"), status_code=303)


