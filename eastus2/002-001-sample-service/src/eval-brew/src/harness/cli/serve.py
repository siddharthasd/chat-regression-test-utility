"""`harness serve` subcommand — launches the FastAPI UI via uvicorn."""

from __future__ import annotations

import logging
import sys

import click


def _resolve_log_level() -> int:
    import os
    return getattr(logging, os.environ.get("LOG_LEVEL", "debug").upper(), logging.DEBUG)


def _configure_harness_logging() -> None:
    """Add a stdout handler to the harness logger hierarchy for server deployments.

    logging_attribution.py intentionally does not install handlers so that
    tests (pytest caplog) and library consumers control output. This function
    is the server entry point's responsibility: it wires harness.* log lines
    to stdout at the LOG_LEVEL env var level before uvicorn's dictConfig runs,
    then disables propagation so uvicorn's root handler doesn't double-print them.

    stdout (not stderr) is used so that container log collectors do not classify
    structured log lines as errors solely because of the output stream.
    """
    harness_logger = logging.getLogger("harness")
    if harness_logger.handlers:
        return  # already configured (e.g., second call in the same process)
    level = _resolve_log_level()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    harness_logger.addHandler(handler)
    harness_logger.setLevel(level)
    harness_logger.propagate = False


@click.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=9000, show_default=True, type=int, help="Bind port.")
def serve(host: str, port: int) -> None:
    """Launch the FastAPI UI via uvicorn on a localhost address."""
    import uvicorn

    _configure_harness_logging()
    uvicorn.run("harness.ui:create_app", host=host, port=port, factory=True)


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(serve)
