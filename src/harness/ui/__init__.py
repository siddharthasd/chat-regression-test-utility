"""Flask UI surface. App factory + blueprints (added by later specs)."""

from __future__ import annotations

from flask import Flask

from harness.bootstrap import initialize_harness
from harness.ui.context_processors import inject_tester_identity


def create_app() -> Flask:
    """Construct the harness Flask app.

    Performs the one-time harness initialization via `initialize_harness(app)`
    before registering any blueprints or routes — so every request handler can
    rely on `IdentityContext.current()` being populated. Registers the
    tester-identity context processor so every template render gets the
    `tester_identity` variable (per 010 FR-005, US3).
    """
    app = Flask(__name__)
    initialize_harness(app)
    app.context_processor(inject_tester_identity)
    # Blueprints / routes are registered by later spec modules (002 dashboard,
    # 003 wizard, 004 detail view, 005 export).
    return app
