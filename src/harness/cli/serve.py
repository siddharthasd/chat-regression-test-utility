"""`harness serve` subcommand — launches the FastAPI UI via uvicorn."""

from __future__ import annotations

import click


@click.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8000, show_default=True, type=int, help="Bind port.")
def serve(host: str, port: int) -> None:
    """Launch the FastAPI UI via uvicorn on a localhost address."""
    import uvicorn

    uvicorn.run("harness.ui:create_app", host=host, port=port, factory=True)


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(serve)
