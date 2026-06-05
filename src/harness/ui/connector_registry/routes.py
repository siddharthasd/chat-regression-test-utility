"""Connector Registry management routes (013). Server-rendered Flask blueprint."""

from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from harness.connector_registry import (
    ConnectorRegistryService,
    RegistrationInUseError,
    parse_connector_form,
    run_test_connection,
)
from harness.connector_registry.test_connection import TestConnectionResult
from harness.persistence import get_session
from harness.persistence.exceptions import HarnessKeyMismatchError

bp = Blueprint("connector_registry", __name__, template_folder="templates")

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
        "archived": reg.archived,
        "updated_at": reg.updated_at,
    }


@bp.route("/connectors", methods=["GET"])
def list_connectors():
    filter_ = request.args.get("filter", "active")
    q = request.args.get("q") or None
    with get_session() as session:
        regs = ConnectorRegistryService(session).list_registrations(filter=filter_, q=q)
        views = [_reg_to_view(r) for r in regs]
    return render_template(
        "connector_registry/list.html", registrations=views, filter=filter_, q=q or "", error=None
    )


@bp.route("/connectors/new", methods=["GET"])
def new_connector():
    return render_template(
        "connector_registry/form.html",
        mode_label="Register new connector",
        reg=None,
        errors={},
        form={},
    )


@bp.route("/connectors", methods=["POST"])
def create_connector():
    payload, errors = parse_connector_form(request.form, require_credential=True)
    if errors:
        return (
            render_template(
                "connector_registry/form.html",
                mode_label="Register new connector",
                reg=None,
                errors=errors,
                form=request.form,
            ),
            400,
        )
    with get_session() as session:
        ConnectorRegistryService(session).create(payload)
    return redirect(url_for("connector_registry.list_connectors"))


@bp.route("/connectors/<connector_id>/edit", methods=["GET"])
def edit_connector(connector_id: str):
    with get_session() as session:
        reg = ConnectorRegistryService(session).get(connector_id)
        if reg is None:
            abort(404)
        view = _reg_to_view(reg)
    return render_template(
        "connector_registry/form.html", mode_label="Edit connector", reg=view, errors={}, form={}
    )


@bp.route("/connectors/<connector_id>", methods=["POST"])
def update_connector(connector_id: str):
    replace = (request.form.get("replace_credential") or "").lower() in _TRUTHY
    with get_session() as session:
        service = ConnectorRegistryService(session)
        existing = service.get(connector_id)
        if existing is None:
            abort(404)
        stored_mode = (existing.auth_descriptor or {}).get("mode")
        new_mode = (request.form.get("auth_mode") or "").strip()
        require_credential = replace or (new_mode != stored_mode)
        payload, errors = parse_connector_form(request.form, require_credential=require_credential)
        if errors:
            view = _reg_to_view(existing)
            return (
                render_template(
                    "connector_registry/form.html",
                    mode_label="Edit connector",
                    reg=view,
                    errors=errors,
                    form=request.form,
                ),
                400,
            )
        service.update(connector_id, payload, replace_credential=require_credential)
    return redirect(url_for("connector_registry.list_connectors"))


@bp.route("/connectors/<connector_id>/archive", methods=["POST"])
def archive_connector(connector_id: str):
    with get_session() as session:
        ConnectorRegistryService(session).archive(connector_id)
    return redirect(url_for("connector_registry.list_connectors"))


@bp.route("/connectors/<connector_id>/restore", methods=["POST"])
def restore_connector(connector_id: str):
    with get_session() as session:
        ConnectorRegistryService(session).restore(connector_id)
    return redirect(url_for("connector_registry.list_connectors"))


@bp.route("/connectors/<connector_id>/delete", methods=["POST"])
def delete_connector(connector_id: str):
    with get_session() as session:
        service = ConnectorRegistryService(session)
        try:
            service.hard_delete(connector_id)
        except RegistrationInUseError as exc:
            views = [_reg_to_view(r) for r in service.list_registrations(filter="all")]
            return (
                render_template(
                    "connector_registry/list.html",
                    registrations=views,
                    filter="all",
                    q="",
                    error=str(exc),
                ),
                409,
            )
    return redirect(url_for("connector_registry.list_connectors"))


@bp.route("/connectors/test-connection", methods=["POST"])
def test_connection_route():
    form = request.form
    endpoint = (form.get("endpoint_url") or "").strip()
    mode = (form.get("auth_mode") or "none").strip()
    try:
        timeout = int(form.get("timeout_seconds") or 30)
    except ValueError:
        timeout = 30
    expects = (form.get("expects_per_row_password") or "").lower() in _TRUTHY
    connector_id = (form.get("connector_id") or "").strip()

    descriptor, needs_stored = _descriptor_from_form(form, mode)
    if needs_stored and connector_id:
        with get_session() as session:
            try:
                descriptor = ConnectorRegistryService(session).get_auth_descriptor_decrypted(
                    connector_id
                )
            except HarnessKeyMismatchError:
                result = TestConnectionResult(
                    False, "auth_decrypt_failed", detail="machine-local key missing or wrong"
                )
                return render_template("connector_registry/_test_result.html", result=result)

    result = run_test_connection(endpoint, descriptor, timeout, expects)
    return render_template("connector_registry/_test_result.html", result=result)


def _descriptor_from_form(form, mode: str) -> tuple[dict, bool]:
    """Build a (decrypted) descriptor from form values. Returns (descriptor, needs_stored)
    where needs_stored signals an edit whose secret wasn't re-entered (decrypt the stored one)."""
    if mode == "bearer":
        token = (form.get("token") or "").strip()
        return {"mode": "bearer", "credential": token}, not token
    if mode == "api-key-header":
        value = (form.get("header_value") or "").strip()
        return {
            "mode": "api-key-header",
            "headerName": (form.get("header_name") or "").strip(),
            "credential": value,
        }, not value
    if mode == "basic":
        password = (form.get("password") or "").strip()
        return {
            "mode": "basic",
            "username": (form.get("username") or "").strip(),
            "password": password,
        }, not password
    if mode == "client-credentials":
        secret = (form.get("client_secret") or "").strip()
        descriptor = {
            "mode": "client-credentials",
            "tokenUrl": (form.get("token_url") or "").strip(),
            "clientId": (form.get("client_id") or "").strip(),
            "clientSecret": secret,
        }
        scope = (form.get("scope") or "").strip()
        audience = (form.get("audience") or "").strip()
        if scope:
            descriptor["scope"] = scope
        if audience:
            descriptor["audience"] = audience
        return descriptor, not secret
    return {"mode": "none"}, False
