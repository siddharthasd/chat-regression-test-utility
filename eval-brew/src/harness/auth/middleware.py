"""FastAPI auth middleware — current_user(), require_auth, require_role."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from harness.auth.config import is_auth_enabled
from harness.auth.session import clear_session_user, get_session_user


def current_user(request: Request) -> dict:
    """Return a user dict for the current request.

    When auth is disabled, returns a synthetic admin user based on the
    IdentityContext singleton (the OS-resolved tester identity).
    When auth is enabled, returns the session user or None.
    """
    if not is_auth_enabled():
        from harness.identity.context import IdentityContext

        try:
            name = IdentityContext.current().value
        except RuntimeError:
            name = "local"
        return {"oid": None, "email": None, "display_name": name, "role": "admin"}
    return get_session_user(request)


async def _require_auth_dep(request: Request) -> dict:
    """FastAPI dependency: ensure the request has an authenticated session user."""
    if not is_auth_enabled():
        return current_user(request)

    user = get_session_user(request)
    if user is None:
        request.session["next"] = str(request.url)
        raise HTTPException(
            status_code=302,
            headers={"Location": str(request.url_for("login"))},
        )

    from harness.persistence import get_session as db_session
    from harness.persistence.repositories.user_registration import UserRegistrationRepository

    with db_session() as db:
        reg = UserRegistrationRepository(db).find_by_oid(user["oid"])

    if reg is None:
        clear_session_user(request)
        request.session.clear()
        raise HTTPException(
            status_code=302,
            headers={"Location": str(request.url_for("unauthorised"))},
        )

    return user


def require_auth(
    request: Request,
    user: Annotated[dict, Depends(_require_auth_dep)] = None,
) -> dict:
    """FastAPI Depends-compatible auth guard (no role restriction)."""
    return user


def require_role(*roles: str):
    """Return a FastAPI Depends-compatible auth guard that also checks role membership."""

    async def _check(
        request: Request,
        user: Annotated[dict, Depends(_require_auth_dep)] = None,
    ) -> dict:
        if not is_auth_enabled():
            return user
        if not user or user.get("role") not in roles:
            raise HTTPException(status_code=403)
        return user

    return _check
