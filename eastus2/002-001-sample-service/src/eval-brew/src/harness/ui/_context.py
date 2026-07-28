"""Per-request template context helper for FastAPI harness UI."""
from __future__ import annotations

from fastapi import Request

from harness.auth.config import is_auth_enabled


def ctx(request: Request) -> dict:
    """Return a dict of common template variables injected into every response."""
    from harness.auth.middleware import current_user

    user = current_user(request)
    flashes = request.session.pop("_flash", [])
    return {
        "tester_identity": user["display_name"] if user else "Unknown",
        "current_user": user,
        "auth_enabled": is_auth_enabled(),
        "flashes": flashes,
    }
