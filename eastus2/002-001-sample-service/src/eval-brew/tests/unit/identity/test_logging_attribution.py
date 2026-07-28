"""US4 unit tests — log-line attribution (FR-006).

Verifies every log line emitted via structlog carries the bound tester_identity
field, and that the identity does not drift within a single process.

Uses `structlog.testing.LogCapture` — the canonical structlog test fixture
that captures events as parsed dicts so assertions on the structured field
name + value are exact (not substring greps on rendered strings).
"""

from __future__ import annotations

import logging

import pytest
import structlog
from structlog.testing import LogCapture

from harness.identity.logging_attribution import configure_structlog_with_identity


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    """Reset structlog + contextvars + stdlib root logger between tests."""
    root = logging.getLogger()
    prior_level = root.level
    prior_handlers = list(root.handlers)
    yield
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()
    root.setLevel(prior_level)
    for h in list(root.handlers):
        if h not in prior_handlers:
            root.removeHandler(h)


@pytest.fixture
def log_capture() -> LogCapture:
    """Capture structlog events as parsed dicts via LogCapture."""
    cap = LogCapture()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            cap,  # Terminal processor — captures event dicts; nothing renders.
        ]
    )
    return cap


def test_every_log_line_carries_identity_field(log_capture: LogCapture) -> None:
    """FR-006: a log line emitted after binding carries the tester_identity field."""
    structlog.contextvars.bind_contextvars(tester_identity="alice")

    logger = structlog.get_logger("test")
    logger.info("first event", action="boot")
    logger.warning("second event", code=42)
    logger.error("third event")

    assert len(log_capture.entries) == 3
    for entry in log_capture.entries:
        assert entry["tester_identity"] == "alice", (
            f"Log entry missing/wrong tester_identity binding: {entry!r}"
        )


def test_no_drift_within_process(log_capture: LogCapture) -> None:
    """SC-005: every log line from a single process attributes to the same identity."""
    structlog.contextvars.bind_contextvars(tester_identity="alice")

    structlog.get_logger("module.a").info("from a")
    structlog.get_logger("module.b").info("from b")
    structlog.get_logger("module.a").warning("a again")
    structlog.get_logger("module.b").error("b again")

    identities_seen = {entry["tester_identity"] for entry in log_capture.entries}
    assert identities_seen == {"alice"}, (
        f"Mid-process drift — multiple identities in logs: {identities_seen}"
    )


def test_binding_persists_across_modules(log_capture: LogCapture) -> None:
    """The context binding propagates to loggers in different modules."""
    structlog.contextvars.bind_contextvars(tester_identity="bob")

    for name in ("harness.connector", "harness.evaluator", "harness.dashboard"):
        structlog.get_logger(name).info("event from " + name)

    assert len(log_capture.entries) == 3
    for entry in log_capture.entries:
        assert entry["tester_identity"] == "bob"


def test_configure_does_not_wipe_other_contextvars() -> None:
    """`configure_structlog_with_identity` selectively binds `tester_identity`
    only; existing contextvars from other modules MUST survive."""
    # Pre-bind a contextvar that another module (e.g., 012 orchestrator) might set.
    structlog.contextvars.bind_contextvars(job_id="job-42")

    configure_structlog_with_identity("alice")

    current = structlog.contextvars.get_contextvars()
    assert current.get("tester_identity") == "alice"
    assert current.get("job_id") == "job-42", (
        "configure_structlog_with_identity wiped a pre-existing contextvar — "
        "violates the selective-bind contract."
    )


def test_configure_does_not_install_root_handler() -> None:
    """The function MUST NOT install a stdlib root-logger handler globally —
    that's the entry point's responsibility, not the binding library's."""
    root = logging.getLogger()
    prior_handler_count = len(root.handlers)

    configure_structlog_with_identity("alice")

    assert len(root.handlers) == prior_handler_count, (
        "configure_structlog_with_identity installed a stdlib root handler — "
        "this is the entry point's responsibility, not the binding library's."
    )
