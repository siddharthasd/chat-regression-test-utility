"""Form parsing + validation for evaluator registrations (FR-002/004/005/007-011).

Mirrors connector_registry.forms; adds ordered declared-dimension parsing and a
required description. Maps to the canonical auth descriptor (009/remote.auth).
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

AUTH_MODES = ("none", "bearer", "api-key-header", "basic")
TIMEOUT_MIN, TIMEOUT_MAX = 1, 600


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_dimensions(text: str | None) -> list[str]:
    """Newline-separated → trimmed, ordered list with blank lines dropped (FR-007/008/011)."""
    dimensions: list[str] = []
    for line in (text or "").splitlines():
        name = line.strip()
        if name:
            dimensions.append(name)
    return dimensions


def duplicate_dimensions(dimensions: list[str]) -> list[str]:
    """Names that appear more than once, first-seen order (FR-009 — non-blocking warning)."""
    seen: set[str] = set()
    dups: list[str] = []
    for name in dimensions:
        if name in seen and name not in dups:
            dups.append(name)
        seen.add(name)
    return dups


def parse_evaluator_form(
    form: Mapping, *, require_credential: bool = True
) -> tuple[dict | None, dict[str, str]]:
    errors: dict[str, str] = {}

    display_name = (form.get("display_name") or "").strip()
    if not display_name:
        errors["display_name"] = "Display name is required."

    description = (form.get("description") or "").strip()
    if not description:
        errors["description"] = "Description is required."

    endpoint_url = (form.get("endpoint_url") or "").strip()
    if not endpoint_url:
        errors["endpoint_url"] = "Endpoint URL is required."
    elif not _valid_url(endpoint_url):
        errors["endpoint_url"] = "Endpoint URL must be a valid http:// or https:// URL."

    mode = (form.get("auth_mode") or "").strip()
    if mode not in AUTH_MODES:
        errors["auth_mode"] = "Select a valid auth mode."

    raw_timeout = (form.get("timeout_seconds") or "").strip()
    timeout = 60
    try:
        timeout = int(raw_timeout) if raw_timeout else 60
        if not TIMEOUT_MIN <= timeout <= TIMEOUT_MAX:
            errors["timeout_seconds"] = (
                f"Timeout must be between {TIMEOUT_MIN} and {TIMEOUT_MAX} seconds."
            )
    except ValueError:
        errors["timeout_seconds"] = "Timeout must be an integer."

    dimensions = parse_dimensions(form.get("dimensions"))

    descriptor = None
    if mode in AUTH_MODES:
        descriptor = _build_descriptor(mode, form, errors, require_credential)

    if errors:
        return None, errors
    return {
        "display_name": display_name,
        "description": description,
        "endpoint_url": endpoint_url,
        "auth_descriptor": descriptor,
        "timeout_seconds": timeout,
        "declared_scoring_dimensions": dimensions,
    }, {}


def _build_descriptor(
    mode: str, form: Mapping, errors: dict[str, str], require_credential: bool
) -> dict:
    if mode == "none":
        return {"mode": "none"}
    if mode == "bearer":
        token = (form.get("token") or "").strip()
        if require_credential and not token:
            errors["token"] = "Bearer token is required."
        return {"mode": "bearer", "credential": token}
    if mode == "api-key-header":
        header_name = (form.get("header_name") or "").strip()
        header_value = (form.get("header_value") or "").strip()
        if not header_name:
            errors["header_name"] = "Header name is required."
        if require_credential and not header_value:
            errors["header_value"] = "Header value is required."
        return {"mode": "api-key-header", "headerName": header_name, "credential": header_value}
    # basic
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()
    if not username:
        errors["username"] = "Username is required."
    if require_credential and not password:
        errors["password"] = "Password is required."
    return {"mode": "basic", "username": username, "password": password}
