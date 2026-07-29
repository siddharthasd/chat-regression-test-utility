"""FastAPI UI surface. App factory + routers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from harness.ui.security_headers import SecurityHeadersMiddleware

from harness.bootstrap import initialize_harness


@asynccontextmanager
async def _lifespan(app: FastAPI):
    import logging
    import sys

    # Wire harness.* log lines to stdout when running under a direct ASGI server
    # (gunicorn, uvicorn without the CLI wrapper). The CLI path is handled by
    # harness_group() in harness.cli. Skip when pytest is active so caplog
    # (which installs a handler on the root logger) can still capture harness.*
    # records via propagation. stdout (not stderr) prevents container log
    # collectors from classifying structured lines as errors by stream alone.
    if "pytest" not in sys.modules:
        import os
        level = getattr(logging, os.environ.get("LOG_LEVEL", "debug").upper(), logging.DEBUG)
        h = logging.getLogger("harness")
        if not h.handlers:
            _h = logging.StreamHandler(sys.stdout)
            _h.setLevel(level)
            h.addHandler(_h)
            h.setLevel(level)
            h.propagate = False

    from harness.ui.admin.log_store import install as _install_log_store, record_audit as _record_audit

    _install_log_store()

    initialize_harness()

    _record_audit("system", "server.startup", "harness process initialised")
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

    # https_only defaults to True (production-safe); set HARNESS_SESSION_HTTPS_ONLY=false
    # in test environments where TestClient speaks plain HTTP.
    https_only = os.environ.get("HARNESS_SESSION_HTTPS_ONLY", "true").lower() != "false"
    app.add_middleware(SessionMiddleware, secret_key=secret_key, https_only=https_only, same_site="lax")
    app.add_middleware(SecurityHeadersMiddleware)
    # Prevent Host-header injection / open-redirect via spoofed Host.
    # Set HARNESS_ALLOWED_HOSTS to a comma-separated list of valid hostnames in production.
    _raw = os.environ.get("HARNESS_ALLOWED_HOSTS", "*")
    _allowed_hosts = [h.strip() for h in _raw.split(",")]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)

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
