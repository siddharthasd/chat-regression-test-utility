"""`harness mock-evaluator` — launch the bundled mock evaluator service (FR-022)."""

from __future__ import annotations

import click

from harness.evaluator import mock as mock_service


@click.command("mock-evaluator")
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8901, type=int, help="Bind port (0 = pick a free one).")
@click.option(
    "--mode",
    default="ok",
    type=click.Choice(mock_service.MODES),
    help="Response behavior: ok | nonconformant | status500 | slow | unexpected_dims.",
)
@click.option("--dimensions", default="", help="Comma-separated declared scoring dimensions.")
@click.option("--slow-seconds", default=5, type=int, help="Sleep for --mode slow.")
def mock_evaluator(host: str, port: int, mode: str, dimensions: str, slow_seconds: int) -> None:
    """Run the bundled mock evaluator service (Ctrl-C to stop)."""
    dims = [d.strip() for d in dimensions.split(",") if d.strip()] or None
    server = mock_service.make_server(host, port, mode, dims, slow_seconds)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    click.echo(f"mock evaluator listening on http://{bound_host}:{bound_port} (mode={mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        click.echo("mock evaluator stopped")


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(mock_evaluator)
