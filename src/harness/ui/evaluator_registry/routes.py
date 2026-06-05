"""Evaluator Registry management routes (014). Mirrors the connector registry blueprint."""

from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for

from harness.evaluator_registry import (
    EvaluatorRegistryService,
    RegistrationInUseError,
    parse_evaluator_form,
    run_test_connection,
)
from harness.evaluator_registry.forms import parse_dimensions
from harness.evaluator_registry.test_connection import TestConnectionResult
from harness.persistence import get_session
from harness.persistence.exceptions import HarnessKeyMismatchError

bp = Blueprint("evaluator_registry", __name__, template_folder="templates")

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
        "archived": reg.archived,
        "updated_at": reg.updated_at,
    }


@bp.route("/evaluators", methods=["GET"])
def list_evaluators():
    filter_ = request.args.get("filter", "active")
    q = request.args.get("q") or None
    with get_session() as session:
        regs = EvaluatorRegistryService(session).list_registrations(filter=filter_, q=q)
        views = [_reg_to_view(r) for r in regs]
    return render_template(
        "evaluator_registry/list.html", registrations=views, filter=filter_, q=q or "", error=None
    )


@bp.route("/evaluators/new", methods=["GET"])
def new_evaluator():
    return render_template(
        "evaluator_registry/form.html",
        mode_label="Register new evaluator",
        reg=None,
        errors={},
        form={},
    )


@bp.route("/evaluators", methods=["POST"])
def create_evaluator():
    payload, errors = parse_evaluator_form(request.form, require_credential=True)
    if errors:
        return (
            render_template(
                "evaluator_registry/form.html",
                mode_label="Register new evaluator",
                reg=None,
                errors=errors,
                form=request.form,
            ),
            400,
        )
    with get_session() as session:
        EvaluatorRegistryService(session).create(payload)
    return redirect(url_for("evaluator_registry.list_evaluators"))


@bp.route("/evaluators/<evaluation_agent_id>/edit", methods=["GET"])
def edit_evaluator(evaluation_agent_id: str):
    with get_session() as session:
        reg = EvaluatorRegistryService(session).get(evaluation_agent_id)
        if reg is None:
            abort(404)
        view = _reg_to_view(reg)
    return render_template(
        "evaluator_registry/form.html", mode_label="Edit evaluator", reg=view, errors={}, form={}
    )


@bp.route("/evaluators/<evaluation_agent_id>", methods=["POST"])
def update_evaluator(evaluation_agent_id: str):
    replace = (request.form.get("replace_credential") or "").lower() in _TRUTHY
    with get_session() as session:
        service = EvaluatorRegistryService(session)
        existing = service.get(evaluation_agent_id)
        if existing is None:
            abort(404)
        stored_mode = (existing.auth_descriptor or {}).get("mode")
        new_mode = (request.form.get("auth_mode") or "").strip()
        require_credential = replace or (new_mode != stored_mode)
        payload, errors = parse_evaluator_form(request.form, require_credential=require_credential)
        if errors:
            view = _reg_to_view(existing)
            return (
                render_template(
                    "evaluator_registry/form.html",
                    mode_label="Edit evaluator",
                    reg=view,
                    errors=errors,
                    form=request.form,
                ),
                400,
            )
        service.update(evaluation_agent_id, payload, replace_credential=require_credential)
    return redirect(url_for("evaluator_registry.list_evaluators"))


@bp.route("/evaluators/<evaluation_agent_id>/archive", methods=["POST"])
def archive_evaluator(evaluation_agent_id: str):
    with get_session() as session:
        EvaluatorRegistryService(session).archive(evaluation_agent_id)
    return redirect(url_for("evaluator_registry.list_evaluators"))


@bp.route("/evaluators/<evaluation_agent_id>/restore", methods=["POST"])
def restore_evaluator(evaluation_agent_id: str):
    with get_session() as session:
        EvaluatorRegistryService(session).restore(evaluation_agent_id)
    return redirect(url_for("evaluator_registry.list_evaluators"))


@bp.route("/evaluators/<evaluation_agent_id>/delete", methods=["POST"])
def delete_evaluator(evaluation_agent_id: str):
    with get_session() as session:
        service = EvaluatorRegistryService(session)
        try:
            service.hard_delete(evaluation_agent_id)
        except RegistrationInUseError as exc:
            views = [_reg_to_view(r) for r in service.list_registrations(filter="all")]
            return (
                render_template(
                    "evaluator_registry/list.html",
                    registrations=views,
                    filter="all",
                    q="",
                    error=str(exc),
                ),
                409,
            )
    return redirect(url_for("evaluator_registry.list_evaluators"))


@bp.route("/evaluators/test-connection", methods=["POST"])
def test_connection_route():
    form = request.form
    endpoint = (form.get("endpoint_url") or "").strip()
    mode = (form.get("auth_mode") or "none").strip()
    try:
        timeout = int(form.get("timeout_seconds") or 60)
    except ValueError:
        timeout = 60
    dimensions = parse_dimensions(form.get("dimensions"))
    evaluation_agent_id = (form.get("evaluation_agent_id") or "").strip()

    descriptor, needs_stored = _descriptor_from_form(form, mode)
    if needs_stored and evaluation_agent_id:
        with get_session() as session:
            try:
                descriptor = EvaluatorRegistryService(session).get_auth_descriptor_decrypted(
                    evaluation_agent_id
                )
            except HarnessKeyMismatchError:
                result = TestConnectionResult(
                    False, "auth_decrypt_failed", detail="machine-local key missing or wrong"
                )
                return render_template("evaluator_registry/_test_result.html", result=result)

    result = run_test_connection(endpoint, descriptor, timeout, dimensions)
    return render_template("evaluator_registry/_test_result.html", result=result)


def _descriptor_from_form(form, mode: str) -> tuple[dict, bool]:
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
