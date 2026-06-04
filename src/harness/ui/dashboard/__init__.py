"""Dashboard & Job Listing Flask blueprint (002) — the harness root page.

Registered into the app by `harness.ui.create_app()`.
"""

from __future__ import annotations

from harness.ui.dashboard.routes import bp

__all__ = ["bp"]
