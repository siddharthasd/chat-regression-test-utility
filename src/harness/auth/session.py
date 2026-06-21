"""Session helpers — get/set/clear user and auth-flow state in the request session."""
from __future__ import annotations

from starlette.requests import Request

_SESSION_KEY = "user"
_AUTH_FLOW_KEY = "auth_flow"


def get_session_user(request: Request) -> dict | None:
    """Return the authenticated user dict from the session, or None."""
    return request.session.get(_SESSION_KEY)


def set_session_user(
    request: Request,
    *,
    oid: str,
    email: str,
    display_name: str,
    role: str,
) -> None:
    """Write the authenticated user dict into the session."""
    request.session[_SESSION_KEY] = {
        "oid": oid,
        "email": email,
        "display_name": display_name,
        "role": role,
    }


def clear_session_user(request: Request) -> None:
    """Remove the authenticated user from the session."""
    request.session.pop(_SESSION_KEY, None)


def get_auth_flow(request: Request) -> dict | None:
    """Return the MSAL auth flow state dict from the session, or None."""
    return request.session.get(_AUTH_FLOW_KEY)


def set_auth_flow(request: Request, flow: dict) -> None:
    """Persist the MSAL auth flow state dict in the session."""
    request.session[_AUTH_FLOW_KEY] = flow


def clear_auth_flow(request: Request) -> None:
    """Remove the MSAL auth flow state from the session."""
    request.session.pop(_AUTH_FLOW_KEY, None)
