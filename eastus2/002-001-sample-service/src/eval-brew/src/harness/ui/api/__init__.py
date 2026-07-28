"""Headless Execution API (020) — programmatic eval-brew access.

Exposes `create_api_router()` for mounting by `harness.ui.create_app()`.
"""

from __future__ import annotations

from fastapi import APIRouter


def create_api_router() -> APIRouter:
    """Return the /api/headless router with all sub-routes registered."""
    from harness.ui.api.routes.connectors import router as connectors_router
    from harness.ui.api.routes.evaluators import router as evaluators_router
    from harness.ui.api.routes.jobs import router as jobs_router

    router = APIRouter(prefix="/api/headless", tags=["headless"])
    router.include_router(connectors_router)
    router.include_router(evaluators_router)
    router.include_router(jobs_router)
    return router
