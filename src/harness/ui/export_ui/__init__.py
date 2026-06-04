"""Results Export Flask blueprint (005). Streams downloads; the control lives on 004's page.

Registered into the app by `harness.ui.create_app()`.
"""

from __future__ import annotations

from harness.ui.export_ui.routes import bp

__all__ = ["bp"]
