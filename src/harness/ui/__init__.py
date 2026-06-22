"""FastAPI UI surface. App factory + routers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from harness.bootstrap import initialize_harness


@asynccontextmanager
async def _lifespan(app: FastAPI):
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

    app.add_middleware(SessionMiddleware, secret_key=secret_key)

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

    return app
