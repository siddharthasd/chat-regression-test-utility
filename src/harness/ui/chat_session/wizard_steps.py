"""Per-step validation for the Chat Session creation wizard (017 US1)."""

from __future__ import annotations


def validate_step1(form: dict) -> dict[str, str]:
    """Step 1: session name must be non-empty."""
    errors: dict[str, str] = {}
    name = (form.get("session_name") or "").strip()
    if not name:
        errors["session_name"] = "Session name is required."
    return errors


def validate_step2(form: dict, connector) -> dict[str, str]:
    """Step 2: a connector must be selected and must support SSE."""
    errors: dict[str, str] = {}
    connector_id = (form.get("connector_id") or "").strip()
    if not connector_id:
        errors["connector_id"] = "Please select a connector."
        return errors
    if connector is None:
        errors["connector_id"] = "Selected connector not found."
        return errors
    if not connector.supports_sse:
        errors["connector_id"] = "Selected connector does not support SSE streaming."
    return errors


def validate_step3(form: dict) -> dict[str, str]:
    """Step 3: test_id and password are both required."""
    errors: dict[str, str] = {}
    if not (form.get("test_id") or "").strip():
        errors["test_id"] = "Test ID is required."
    if not (form.get("password") or "").strip():
        errors["password"] = "Password is required."
    return errors


def validate_step4(form: dict, evaluator) -> dict[str, str]:
    """Step 4: an evaluator must be selected and must support SSE."""
    errors: dict[str, str] = {}
    evaluator_id = (form.get("evaluator_id") or "").strip()
    if not evaluator_id:
        errors["evaluator_id"] = "Please select an evaluator."
        return errors
    if evaluator is None:
        errors["evaluator_id"] = "Selected evaluator not found."
        return errors
    if not evaluator.supports_sse:
        errors["evaluator_id"] = "Selected evaluator does not support SSE streaming."
    return errors


def validate_step5(wizard_data: dict) -> dict[str, str]:
    """Step 5 (confirm): verify all prior steps have valid data in session."""
    errors: dict[str, str] = {}
    if not (wizard_data.get("session_name") or "").strip():
        errors["session"] = "Session name is missing. Please restart the wizard."
    if not wizard_data.get("connector_id"):
        errors["session"] = "Connector selection is missing. Please restart the wizard."
    if not (wizard_data.get("test_id") or "").strip():
        errors["session"] = "Test credentials are missing. Please restart the wizard."
    if not wizard_data.get("evaluator_id"):
        errors["session"] = "Evaluator selection is missing. Please restart the wizard."
    return errors
