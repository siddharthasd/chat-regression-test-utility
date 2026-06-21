"""Admin user management routes (015) — RBAC-protected, admin-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from harness.auth.middleware import require_role
from harness.auth.session import get_session_user
from harness.persistence import get_session
from harness.persistence.exceptions import SelfRemovalError
from harness.persistence.repositories.user_registration import UserRegistrationRepository
from harness.ui._context import ctx
from harness.ui._templates import templates

router = APIRouter()

_ROLES = ("admin", "user")


def _flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("_flash", []).append((category, message))


@router.get("/admin/users", name="admin_users")
def admin_users(
    request: Request,
    user: dict = Depends(require_role("admin")),
):
    with get_session() as db:
        registrations = UserRegistrationRepository(db).list_all()
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {"registrations": registrations, **ctx(request)},
    )


@router.get("/admin/users/new", name="admin_new_user")
def admin_new_user(
    request: Request,
    user: dict = Depends(require_role("admin")),
):
    return templates.TemplateResponse(
        request,
        "admin/new_user.html",
        {"roles": _ROLES, **ctx(request)},
    )


@router.post("/admin/users/new", name="admin_create_user")
def admin_create_user(
    request: Request,
    email: str = Form(...),
    role: str = Form(...),
    display_name: str = Form(None),
    user: dict = Depends(require_role("admin")),
):
    if role not in _ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")

    with get_session() as db:
        repo = UserRegistrationRepository(db)
        if repo.find_by_email(email):
            _flash(request, f"{email} is already registered.", "warning")
            return RedirectResponse(request.url_for("admin_users"), status_code=303)
        repo.create(email=email, role=role, display_name=display_name or None)

    _flash(request, f"Registered {email} as {role}.", "success")
    return RedirectResponse(request.url_for("admin_users"), status_code=303)


@router.post("/admin/users/{reg_id}/change-role", name="admin_change_role")
def admin_change_role(
    request: Request,
    reg_id: str,
    role: str = Form(...),
    user: dict = Depends(require_role("admin")),
):
    if role not in _ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")

    with get_session() as db:
        repo = UserRegistrationRepository(db)
        reg = repo.get(reg_id)
        if reg is None:
            raise HTTPException(status_code=404)
        repo.update_role(reg, role)

    _flash(request, f"Role updated to {role}.", "success")
    return RedirectResponse(request.url_for("admin_users"), status_code=303)


@router.post("/admin/users/{reg_id}/remove", name="admin_remove_user")
def admin_remove_user(
    request: Request,
    reg_id: str,
    user: dict = Depends(require_role("admin")),
):
    current = get_session_user(request)
    with get_session() as db:
        repo = UserRegistrationRepository(db)
        reg = repo.get(reg_id)
        if reg is None:
            raise HTTPException(status_code=404)
        if current and reg.azure_oid and reg.azure_oid == current.get("oid"):
            raise SelfRemovalError()
        email = reg.email
        repo.delete(reg)

    _flash(request, f"Removed {email}.", "success")
    return RedirectResponse(request.url_for("admin_users"), status_code=303)
