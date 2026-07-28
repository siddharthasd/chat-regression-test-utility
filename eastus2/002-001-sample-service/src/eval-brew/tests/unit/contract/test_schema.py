"""Schema-artifact tests (T009): structure, documentation, version constant.

Covers FR-001/002/003/014 and research R8 (no version drift).
"""

from __future__ import annotations

from harness.contract.schema import BUNDLED_CONTRACT_VERSION, load_schema

_REQUIRED_TOP = {
    "contractVersion",
    "utteranceId",
    "utteranceText",
    "testId",
    "conversationContext",
    "chatbotResponse",
    "connectorId",
    "timestamp",
}
_REQUIRED_CHATBOT = {"rawPayload", "normalizedText", "agentChain", "metadata"}


def test_schema_loads() -> None:
    schema = load_schema()
    assert schema["type"] == "object"
    assert "$schema" in schema


def test_required_top_level_fields() -> None:
    assert set(load_schema()["required"]) == _REQUIRED_TOP


def test_chatbot_response_required_fields() -> None:
    cr = load_schema()["properties"]["chatbotResponse"]
    assert set(cr["required"]) == _REQUIRED_CHATBOT


def test_additional_properties_left_open() -> None:
    # FR-005: extensibility — no level forbids unknown fields.
    schema = load_schema()
    assert "additionalProperties" not in schema
    assert "additionalProperties" not in schema["properties"]["chatbotResponse"]


def test_every_field_is_documented() -> None:
    # FR-014: human-readable description on every named field.
    props = load_schema()["properties"]
    for name, sub in props.items():
        assert sub.get("description"), f"top-level field {name!r} lacks a description"
    cr_props = props["chatbotResponse"]["properties"]
    for name, sub in cr_props.items():
        assert sub.get("description"), f"chatbotResponse.{name} lacks a description"


def test_bundled_version_matches_schema() -> None:
    # R8: BUNDLED_CONTRACT_VERSION is the single source of truth; must not drift.
    assert int(load_schema()["x-contractVersion"]) == BUNDLED_CONTRACT_VERSION
