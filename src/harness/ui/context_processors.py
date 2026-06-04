"""Flask context processors for the harness UI.

Each function returns a dict whose keys become available as variables in every
template render. Wired into the app via `app.context_processor(...)` in
`harness.ui.create_app()`.
"""

from __future__ import annotations

from harness.identity.context import IdentityContext


def inject_tester_identity() -> dict[str, str]:
    """Inject `tester_identity` into every template render (010 FR-005)."""
    return {"tester_identity": IdentityContext.current().value}
