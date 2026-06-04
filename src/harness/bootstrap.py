"""Process-startup bootstrap.

Performs the one-time initialization that every harness entry point (Flask UI,
CLI) requires:
- Resolves the OS-derived tester identity (per 010 FR-001).
- Installs it as a read-only singleton (per 010 FR-002).
- Binds it into the structlog context for log-line attribution (per 010 FR-006,
  wired in US4 task T028).

Called exactly once per process from the UI app factory (`harness.ui.create_app`)
and from the CLI group callback (`harness.cli.harness_group`). The identity
context's `_initialize_once()` enforcement guarantees no double-initialization
even if a code path calls `initialize_harness()` twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def initialize_harness(app: Flask | None = None) -> None:
    """One-time harness initialization.

    Resolves the OS-derived tester identity (010 FR-001) and installs it as
    the read-only IdentityContext singleton (010 FR-002), then binds the
    identity into structlog's context for log-line attribution (010 FR-006).

    Idempotent: safe to call multiple times within the same process. A
    second call:
      - Does NOT re-resolve the OS identity (the singleton is preserved).
      - Does NOT re-bind structlog (the binding is already in place).
      - DOES write `app.config["TESTER_IDENTITY"]` if an `app` is passed and
        not already populated — this lets the same harness process support
        both a Flask UI and a Click CLI call path with consistent state.

    Threading assumption: the harness is single-threaded at the app-factory
    layer. The `is None` check followed by `_initialize_once()` is NOT
    guarded by a lock, so concurrent calls from multiple threads could race
    and trigger the singleton's RuntimeError on the loser. Acceptable in
    v1 because the Flask dev server + Click CLI are single-threaded at
    boot; if a future deployment uses a threaded WSGI server with
    eager-init, wrap initialization in a `threading.Lock`.

    Args:
        app: Optional Flask app instance. When provided, the function pushes
            the tester identity into `app.config["TESTER_IDENTITY"]` for
            template / context-processor access.
    """
    from harness.identity.context import IdentityContext
    from harness.identity.logging_attribution import configure_structlog_with_identity
    from harness.identity.resolution import resolve_tester_identity

    # Already-initialized path: preserve singleton, populate app.config if asked.
    if IdentityContext._resolved is not None:  # noqa: SLF001  (legitimate idempotence guard)
        if app is not None:
            app.config["TESTER_IDENTITY"] = IdentityContext._resolved.value  # noqa: SLF001
        return

    # First-init path: resolve, install singleton, bind logger, populate app.
    identity = resolve_tester_identity()
    IdentityContext._initialize_once(identity)  # noqa: SLF001  (legitimate single-init call site)
    configure_structlog_with_identity(identity.value)

    # Prepare the persistence layer: apply pending migrations or refuse to start
    # if the on-disk schema is newer than this harness (009 FR-014/FR-016).
    from harness.persistence.engine import init_db

    init_db()

    # Orphan reconciliation: fail any Job left running/cancelling by a prior
    # process before any other module reads persistent state (012 FR-002).
    from harness.orchestrator import reconcile_orphans

    reconcile_orphans()

    if app is not None:
        app.config["TESTER_IDENTITY"] = identity.value
