"""`harness serve` subcommand — launches the Flask UI on localhost."""

from __future__ import annotations

import click


@click.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=5000, show_default=True, type=int, help="Bind port.")
def serve(host: str, port: int) -> None:
    """Launch the Flask UI on a localhost address.

    Log-level configuration is intentionally NOT wired here in v1; it lands
    later when 002/003/004's UI surfaces add their own logging needs.
    """
    # Import inside the command so `harness --help` doesn't trigger Flask import.
    from harness.ui import create_app

    app = create_app()
    app.run(host=host, port=port)


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(serve)
