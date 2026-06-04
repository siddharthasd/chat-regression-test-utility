"""`harness contract validate` — authoring-time contract validation (006 FR-010).

Output shape contract: `specs/006-evaluation-contract/contracts/cli-contract.md`.
Exit codes: 0 conforming, 1 non-conforming, 2 usage error (bad/missing file).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from harness.contract import validate_contract


@click.group("contract")
def contract_group() -> None:
    """Standard Evaluation Contract tools."""


@contract_group.command("validate")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON output.")
def validate(path: Path, as_json: bool) -> None:
    """Validate a JSON file against the Standard Evaluation Contract."""
    try:
        # utf-8-sig tolerates an optional BOM — files written by Windows editors
        # / PowerShell's `Out-File -Encoding utf8` carry one and plain utf-8 +
        # json.loads would choke on it.
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        click.echo(f"cannot read file: {exc}", err=True)
        sys.exit(2)
    try:
        instance = json.loads(text)
    except json.JSONDecodeError as exc:
        click.echo(f"not valid JSON: {exc}", err=True)
        sys.exit(2)

    result = validate_contract(instance)

    if as_json:
        click.echo(
            json.dumps(
                {
                    "valid": result.valid,
                    "contractVersion": result.contract_version,
                    "violations": [
                        {
                            "fieldPath": v.field_path,
                            "kind": str(v.kind),
                            "message": v.message,
                            "expected": v.expected,
                            "observed": v.observed,
                        }
                        for v in result.violations
                    ],
                },
                indent=2,
            )
        )
    elif result.valid:
        click.echo("VALID")
    else:
        click.echo("INVALID")
        for v in result.violations:
            # ASCII separator only — the default Windows console (cp1252) cannot
            # render non-ASCII punctuation (matches the cli/info.py convention).
            click.echo(f"  {v.field_path}: {v.kind} - {v.message}")

    sys.exit(0 if result.valid else 1)


# Register with the top-level group at import time.
from harness.cli import harness_group  # noqa: E402

harness_group.add_command(contract_group)
