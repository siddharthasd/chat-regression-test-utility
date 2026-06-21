"""Admin routes (015/016) — user management + job maintenance, admin-only."""

from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from harness.auth.middleware import require_role
from harness.auth.session import get_session_user
from harness.persistence import get_session
from harness.persistence.engine import resolve_db_path
from harness.persistence.exceptions import SelfRemovalError
from harness.persistence.repositories.job import JobRepository
from harness.persistence.repositories.user_registration import UserRegistrationRepository
from harness.ui._context import ctx
from harness.ui._templates import templates

router = APIRouter()


def _db_size_mb() -> float | str:
    try:
        return round(os.path.getsize(resolve_db_path()) / (1024 * 1024), 2)
    except OSError:
        return "unknown"


def _vacuum_db() -> None:
    # Must use a raw sqlite3 connection — SQLAlchemy's enable_transactional_ddl
    # listener auto-emits BEGIN on every engine connection, and SQLite refuses
    # VACUUM inside an open transaction.
    conn = sqlite3.connect(str(resolve_db_path()))
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


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


# ----------------------------------------------------------------- maintenance
@router.get("/admin/maintenance", name="admin_maintenance")
def admin_maintenance(
    request: Request,
    user: dict = Depends(require_role("admin")),
):
    with get_session() as db:
        repo = JobRepository(db)
        total_jobs = repo.count_all()
        clearable_jobs = repo.count_clearable()
    return templates.TemplateResponse(
        request,
        "admin/maintenance.html",
        {
            "total_jobs": total_jobs,
            "clearable_jobs": clearable_jobs,
            "db_size_mb": _db_size_mb(),
            **ctx(request),
        },
    )


@router.post("/admin/maintenance", name="admin_maintenance_run")
def admin_maintenance_run(
    request: Request,
    user: dict = Depends(require_role("admin")),
):
    size_before = _db_size_mb()
    with get_session() as db:
        deleted = JobRepository(db).delete_all_clearable()
    _vacuum_db()
    size_after = _db_size_mb()
    _flash(
        request,
        f"Deleted {deleted} job(s). Database size: {size_before} MB → {size_after} MB.",
        "success",
    )
    return RedirectResponse(request.url_for("admin_maintenance"), status_code=303)
