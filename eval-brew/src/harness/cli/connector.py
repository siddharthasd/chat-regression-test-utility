"""`harness mock-connector` — launch the bundled mock connector service (FR-018).

A thin Click wrapper over `harness.connector.mock.make_server`.
"""

from __future__ import annotations

import click

from harness.connector import mock as mock_service


@click.command("mock-connector")
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8900, type=int, help="Bind port (0 = pick a free one).")
@click.option(
    "--mode",
    default="ok",
    type=click.Choice(mock_service.MODES),
    help="Response behavior: ok | nonconformant | status500 | slow.",
)
@click.option("--slow-seconds", default=5, type=int, help="Sleep for --mode slow.")
def mock_connector(host: str, port: int, mode: str, slow_seconds: int) -> None:
    """Run the bundled mock connector service (Ctrl-C to stop)."""
    server = mock_service.make_server(host, port, mode, slow_seconds)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    click.echo(f"mock connector listening on http://{bound_host}:{bound_port} (mode={mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        click.echo("mock connector stopped")


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(mock_connector)
