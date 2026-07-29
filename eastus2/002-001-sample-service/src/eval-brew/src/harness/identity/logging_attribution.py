"""structlog binding for tester-identity log-line attribution (010 FR-006).

`configure_structlog_with_identity(identity_value)` is called once at app
startup (from `harness.bootstrap.initialize_harness`, after IdentityContext
is populated). It configures the structlog pipeline to:

  - merge context-vars into every event (the tester_identity binding lives here),
  - render through stdlib logging so pytest's `caplog` fixture + Flask's
    default logging + any user-installed handlers all receive the message.

After this call, every `structlog.get_logger(...)` instance — created in any
module, at any time — emits log lines carrying `tester_identity=<value>` as
a structured field.

Per `research.md` R2, this design lets us swap the rendering processor for
JSON output (machine-readable logs) without touching any caller.
"""

from __future__ import annotations

import sys

import structlog


def _renderer():
    """Return ConsoleRenderer for TTY sessions, JSONRenderer for containers."""
    if sys.stderr.isatty():
        return structlog.dev.ConsoleRenderer()
    return structlog.processors.JSONRenderer()


def configure_structlog_with_identity(identity_value: str) -> None:
    """Configure structlog with tester-identity binding (010 FR-006).

    Idempotent: safe to call multiple times within a process. The function
    selectively binds ONLY the `tester_identity` contextvar — it never wipes
    contextvars bound by other modules (the orchestrator's `job_id`,
    `utterance_id`, etc., which will be added later as 012 lands). This
    preserves layered context bindings.

    Side effects:
      - Configures structlog's processor chain to merge contextvars + render
        through stdlib logging.
      - Does NOT install a stdlib root-logger handler. Handler installation
        is the responsibility of the entry point (Flask app factory's
        `app.logger`, Click's `--log-level`, or pytest's `caplog` fixture).
        This avoids polluting test runs and shared log configuration.
      - Binds (or re-binds) `tester_identity` as a contextvar. Subsequent
        bindings of the SAME key overwrite; bindings of DIFFERENT keys are
        preserved.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _renderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    # Selectively bind ONLY tester_identity. Do NOT clear_contextvars —
    # that would wipe bindings from other modules (e.g., 012's per-row
    # job_id / utterance_id when the orchestrator lands).
    structlog.contextvars.bind_contextvars(tester_identity=identity_value)
