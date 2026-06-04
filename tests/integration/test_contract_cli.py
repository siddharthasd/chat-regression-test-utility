"""`harness contract validate` CLI integration tests (T014/T018, FR-010, SC-008)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from harness.cli import harness_group


def _good() -> dict:
    return {
        "contractVersion": "1",
        "utteranceId": "u-1",
        "utteranceText": "hi",
        "testId": "row-1",
        "conversationContext": None,
        "connectorId": "conn-abc",
        "timestamp": "2026-06-03T12:00:00Z",
        "chatbotResponse": {
            "rawPayload": {},
            "normalizedText": "hello",
            "agentChain": [],
            "metadata": {},
        },
    }


def test_validate_conforming_exit_zero(tmp_path) -> None:
    path = tmp_path / "good.json"
    path.write_text(json.dumps(_good()), encoding="utf-8")
    result = CliRunner().invoke(harness_group, ["contract", "validate", str(path)])
    assert result.exit_code == 0
    assert "VALID" in result.output


def test_validate_nonconforming_exit_one(tmp_path) -> None:
    bad = _good()
    del bad["utteranceId"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    result = CliRunner().invoke(harness_group, ["contract", "validate", str(path)])
    assert result.exit_code == 1
    assert "INVALID" in result.output
    assert "utteranceId" in result.output


def test_validate_json_output(tmp_path) -> None:
    bad = _good()
    bad["contractVersion"] = "2"
    path = tmp_path / "future.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    result = CliRunner().invoke(harness_group, ["contract", "validate", str(path), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["valid"] is False
    assert any(v["kind"] == "version_out_of_range" for v in payload["violations"])


def test_validate_tolerates_utf8_bom(tmp_path) -> None:
    # Files written by Windows tools (PowerShell Out-File -Encoding utf8) carry a
    # UTF-8 BOM; the CLI must still parse them (regression for the utf-8-sig fix).
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_good()).encode("utf-8"))
    result = CliRunner().invoke(harness_group, ["contract", "validate", str(path)])
    assert result.exit_code == 0
    assert "VALID" in result.output


def test_bad_json_exit_two(tmp_path) -> None:
    path = tmp_path / "x.json"
    path.write_text("{not valid json", encoding="utf-8")
    result = CliRunner().invoke(harness_group, ["contract", "validate", str(path)])
    assert result.exit_code == 2


def test_missing_file_exit_two(tmp_path) -> None:
    result = CliRunner().invoke(
        harness_group, ["contract", "validate", str(tmp_path / "nope.json")]
    )
    assert result.exit_code == 2
