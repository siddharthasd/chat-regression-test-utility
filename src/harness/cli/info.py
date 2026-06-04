"""`harness info` subcommand — print diagnostic info per 010 FR-007.

Output shape contract: `specs/010-tester-identity/contracts/harness-info-cli.md`.

Default: JSON object with the three required fields (tester_identity,
tester_identity_resolution_source, harness_version).
--human: left-aligned 3-row tabular text rendering with field labels.
"""

from __future__ import annotations

import json
import sys

import click

from harness import __version__
from harness.identity.context import IdentityContext

# Field-gather helpers. Each returns (key, value) or raises an internal-error.
# Today only required fields exist; future optional fields (database_path,
# python_version, platform) will land here too. Per the harness-info-cli
# contract, an internal error gathering a non-critical field:
#   - omits that field from the output
#   - writes a diagnostic to stderr
#   - causes the overall exit code to be 1
# Required fields (tester_identity*, harness_version) are always present;
# if any required field fails, the entire command fails.


def _gather_required_fields() -> dict[str, str]:
    """Gather the three required fields per harness-info-cli.md."""
    identity = IdentityContext.current()
    return {
        "tester_identity": identity.value,
        "tester_identity_resolution_source": identity.resolution_source,
        "harness_version": __version__,
    }


def _gather_optional_fields() -> tuple[dict[str, str], list[str]]:
    """Gather optional fields; return (fields, errors).

    Each entry in `errors` is a stderr-writable line describing the
    failure for one optional field. The fields dict contains only
    successfully-gathered entries.
    """
    fields: dict[str, str] = {}
    errors: list[str] = []
    # No optional fields in v1; this scaffolding is here so the next
    # optional field landed here doesn't require restructuring info().
    return fields, errors


@click.command("info")
@click.option(
    "--human",
    is_flag=True,
    default=False,
    help="Render as tabular text instead of JSON.",
)
def info(human: bool) -> None:
    """Print harness diagnostic info."""
    try:
        payload = _gather_required_fields()
    except Exception as exc:  # pragma: no cover  (defensive — required fields shouldn't fail)
        click.echo(f"error gathering required fields: {exc}", err=True)
        sys.exit(1)

    optional, optional_errors = _gather_optional_fields()
    payload.update(optional)
    for line in optional_errors:
        click.echo(line, err=True)

    if human:
        # Left-aligned tabular rendering with label:value rows per the
        # harness-info-cli.md contract example.
        labels = [
            ("Tester identity", payload["tester_identity"]),
            ("Resolution source", payload["tester_identity_resolution_source"]),
            ("Harness version", payload["harness_version"]),
        ]
        label_width = max(len(label) for label, _ in labels)
        click.echo("Harness info")
        # ASCII separator for cross-platform terminal compatibility
        # (Windows cp1252 default console can't render U+2500 box-drawing chars).
        click.echo("-" * 12)
        for label, value in labels:
            click.echo(f"{(label + ':').ljust(label_width + 1)}    {value}")
    else:
        click.echo(json.dumps(payload, indent=2))

    # Per contract: any optional-field failure produces exit 1 with stderr detail.
    if optional_errors:
        sys.exit(1)


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(info)
