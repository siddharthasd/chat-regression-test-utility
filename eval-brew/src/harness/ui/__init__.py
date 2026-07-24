"""FastAPI UI surface. App factory + routers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # 'unsafe-inline' retained for compatibility with Jinja2 inline <script> blocks;
        # upgrade to nonce-based CSP once templates are nonce-annotated.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'"
        )
        return response

from harness.bootstrap import initialize_harness


@asynccontextmanager
async def _lifespan(app: FastAPI):
    import logging
    import sys

    # Wire harness.* log lines to stderr when running under a direct ASGI server
    # (gunicorn, uvicorn without the CLI wrapper). The CLI path is handled by
    # harness_group() in harness.cli. Skip when pytest is active so caplog
    # (which installs a handler on the root logger) can still capture harness.*
    # records via propagation.
    if "pytest" not in sys.modules:
        h = logging.getLogger("harness")
        if not h.handlers:
            _h = logging.StreamHandler()
            _h.setLevel(logging.INFO)
            h.addHandler(_h)
            h.setLevel(logging.INFO)
            h.propagate = False

    initialize_harness()
    yield


def create_app() -> FastAPI:
    """Construct the harness FastAPI app.

    Performs the one-time harness initialization via `initialize_harness()`
    in the lifespan hook, then mounts all domain routers.
    """
    import os
    from pathlib import Path

    from harness.auth.config import get_auth_config

    cfg = get_auth_config()
    secret_key = cfg.get("secret_key") or os.urandom(32).hex()

    app = FastAPI(lifespan=_lifespan, title="AI Regression Test Harness")

    app.add_middleware(SessionMiddleware, secret_key=secret_key, https_only=True, same_site="lax")
    app.add_middleware(_SecurityHeadersMiddleware)

    # Static files
    _static_dir = Path(__file__).parent / "static"
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    # Domain routers
    from harness.ui.connector_registry import router as connector_registry_router
    from harness.ui.dashboard import router as dashboard_router
    from harness.ui.detail import router as detail_router
    from harness.ui.evaluator_registry import router as evaluator_registry_router
    from harness.ui.export_ui import router as export_router
    from harness.ui.wizard import router as wizard_router

    app.include_router(dashboard_router)
    app.include_router(connector_registry_router)
    app.include_router(evaluator_registry_router)
    app.include_router(wizard_router)
    app.include_router(detail_router)
    app.include_router(export_router)

    # Chat session module (017)
    from harness.ui.chat_session import router as chat_session_router

    app.include_router(chat_session_router)

    # Auth and admin routers — always included; handlers check is_auth_enabled() internally
    from harness.ui.admin import router as admin_router
    from harness.ui.auth import router as auth_router
    from harness.ui.docs_ui import router as docs_router

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(docs_router)

    # Headless API (020) — Bearer JWT auth, no session cookie required
    from harness.ui.api import create_api_router

    app.include_router(create_api_router())

    return app
