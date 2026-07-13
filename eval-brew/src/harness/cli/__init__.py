"""Click CLI entry point.

The `harness` command (registered via `[project.scripts]` in `pyproject.toml`)
is the Click group `harness_group` defined here. Subcommands live in sibling
modules (`serve.py`, `info.py`, etc.) and register themselves into the group.
"""

from __future__ import annotations

import click

from harness.bootstrap import initialize_harness


@click.group()
def harness_group() -> None:
    """AI Chatbot Regression Test Harness.

    Run `harness <subcommand>`. See `harness --help` for the subcommand list.
    """
    # Wire harness.* log lines to stderr before initialize_harness() fires, so
    # startup log lines (db.backend, db.migrations.*, startup.complete) are
    # visible. Lazy import avoids a circular reference at module-load time; by
    # call time all CLI submodules are fully imported. (harness.cli.serve imports
    # harness.cli, but that module is already cached in sys.modules here.)
    from harness.cli.serve import _configure_harness_logging  # noqa: PLC0415
    _configure_harness_logging()

    # Initialize the harness for every CLI invocation. Each CLI invocation is a
    # separate process, so `IdentityContext._initialize_once()` fires exactly
    # once per process across both the CLI and UI surfaces (per
    # contracts/harness-info-cli.md's separate-processes rule).
    initialize_harness()


# Subcommand registration — kept here so importing harness.cli is enough to
# wire everything in. Subcommand modules call `harness_group.add_command(...)`
# at import time.
from harness.cli import (  # noqa: E402, F401  (registers subcommands)
    connector,
    contract,
    evaluator,
    info,
    serve,
    users,
)
