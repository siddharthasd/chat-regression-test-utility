"""US5 integration tests — `harness info` CLI output (FR-007).

Verifies the contract documented in `specs/010-tester-identity/contracts/harness-info-cli.md`:
- JSON output by default with three required fields.
- `--human` flag produces a tabular text rendering with the same data.
- Both modes work with stub-installed identities.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from harness import __version__
from harness.cli import harness_group


@pytest.fixture(autouse=True)
def reset_identity_context() -> None:
    """Reset the singleton between tests so each test resolves cleanly via the
    CLI group callback. (The stub_identity fixture overrides the value AFTER
    the group callback runs, which is what we want.)"""
    from harness.identity.context import IdentityContext

    yield
    IdentityContext._resolved = None


def test_info_default_json_output(stub_identity) -> None:
    """FR-007 + harness-info-cli.md: default invocation produces valid JSON
    with the three required fields populated."""
    stub_identity.with_identity("alice")
    runner = CliRunner()

    result = runner.invoke(harness_group, ["info"])

    assert result.exit_code == 0, f"non-zero exit: {result.output}"
    payload = json.loads(result.output)
    assert payload["tester_identity"] == "alice"
    assert payload["tester_identity_resolution_source"] == "stub"
    assert payload["harness_version"] == __version__


def test_info_human_flag_renders_table(stub_identity) -> None:
    """`--human` produces tabular text with all three labels (with trailing colon
    per harness-info-cli.md example)."""
    stub_identity.with_identity("bob")
    runner = CliRunner()

    result = runner.invoke(harness_group, ["info", "--human"])

    assert result.exit_code == 0
    output = result.output
    # The output is NOT JSON (no leading `{`)
    assert not output.lstrip().startswith("{")
    # All three labels visible WITH the trailing colon per contract example
    assert "Tester identity:" in output
    assert "Resolution source:" in output
    assert "Harness version:" in output
    # And the values
    assert "bob" in output
    assert "stub" in output
    assert __version__ in output


def test_info_unknown_user_default(stub_identity) -> None:
    """The 'unknown-user' literal flows through cleanly."""
    stub_identity.with_identity("unknown-user")
    runner = CliRunner()

    result = runner.invoke(harness_group, ["info"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["tester_identity"] == "unknown-user"
