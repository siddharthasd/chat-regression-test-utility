"""Form parsing + validation for evaluator registrations (FR-002/004/005/007-011).

Mirrors connector_registry.forms; adds ordered declared-dimension parsing.
Maps to the canonical auth descriptor (009/remote.auth).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlparse

AUTH_MODES = ("none", "bearer", "api-key-header", "basic", "client-credentials")
TIMEOUT_MIN, TIMEOUT_MAX = 1, 600
_TRUTHY = {"1", "true", "on", "yes"}


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
    """Names that appear more than once, first-seen order."""
    seen: set[str] = set()
    dups: list[str] = []
    for name in dimensions:
        if name in seen and name not in dups:
            dups.append(name)
        seen.add(name)
    return dups


def parse_thresholds_field(raw: str | None) -> tuple[dict | None, str | None]:
    """Parse and validate JSON threshold declaration.

    Returns (thresholds_dict, error). Blank → (None, None).
    """
    stripped = (raw or "").strip()
    if not stripped:
        return None, None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, 'Must be a JSON object mapping dimension names to {"pass": N, "warn": N}.'
    for dim, bounds in data.items():
        if not isinstance(bounds, dict):
            return None, f"Threshold for '{dim}' must be an object with 'pass' and 'warn' keys."
        for key in ("pass", "warn"):
            if key not in bounds:
                return None, f"Threshold for '{dim}' is missing the '{key}' key."
            val = bounds[key]
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                return None, f"Threshold '{key}' for '{dim}' must be a number."
        if bounds["pass"] <= bounds["warn"]:
            return None, (
                f"'pass' threshold ({bounds['pass']}) for '{dim}' must be strictly "
                f"greater than 'warn' threshold ({bounds['warn']})."
            )
    return data, None


def parse_scale_field(raw: str | None) -> tuple[float | None, str | None]:
    """Return (value, error). Blank → (None, None). Non-numeric → (None, message)."""
    stripped = (raw or "").strip()
    if not stripped:
        return None, None
    try:
        return float(stripped), None
    except ValueError:
        return None, "Must be a numeric value (e.g. 0, 0.5, 10)."


def parse_evaluator_form(
    form: Mapping, *, require_credential: bool = True
) -> tuple[dict | None, dict[str, str]]:
    errors: dict[str, str] = {}

    display_name = (form.get("display_name") or "").strip()
    if not display_name:
        errors["display_name"] = "Display name is required."

    description = (form.get("description") or "").strip()

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
    supports_sse = (form.get("supports_sse") or "").strip().lower() in _TRUTHY

    # FR-007 — numeric parse first, regardless of dimension count
    scale_min, err_min = parse_scale_field(form.get("score_scale_min"))
    scale_max, err_max = parse_scale_field(form.get("score_scale_max"))
    if err_min:
        errors["score_scale_min"] = err_min
    if err_max:
        errors["score_scale_max"] = err_max

    # FR-001 — hard cap at 10 dimensions
    if len(dimensions) > 10:
        errors["dimensions"] = (
            f"Maximum 10 dimensions allowed ({len(dimensions)} declared)."
        )

    # FR-002 — duplicate names are now a blocking error (was non-blocking warning)
    if "dimensions" not in errors:
        dups = duplicate_dimensions(dimensions)
        if dups:
            quoted = ", ".join(f"'{d}'" for d in dups)
            errors["dimensions"] = (
                f"Dimension names must be unique. Duplicate(s): {quoted}."
            )

    # FR-005 — scale required when at least one dimension is declared
    if len(dimensions) > 0 and not errors.get("score_scale_min") and not errors.get("score_scale_max"):
        if scale_min is None or scale_max is None:
            msg = "Score minimum and maximum are required when dimensions are declared."
            if scale_min is None:
                errors["score_scale_min"] = msg
            if scale_max is None:
                errors["score_scale_max"] = msg

    # FR-006 — scale_min must be strictly less than scale_max
    if (
        scale_min is not None
        and scale_max is not None
        and not errors.get("score_scale_min")
        and not errors.get("score_scale_max")
        and scale_min >= scale_max
    ):
        errors["score_scale_min"] = "Score minimum must be strictly less than Score maximum."

    thresholds, err_thresholds = parse_thresholds_field(form.get("scoring_thresholds_json"))
    if err_thresholds:
        errors["scoring_thresholds"] = err_thresholds

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
        "supports_sse": supports_sse,
        "score_scale_min": scale_min,
        "score_scale_max": scale_max,
        "scoring_thresholds": thresholds,
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
    if mode == "client-credentials":
        return _build_client_credentials(form, errors, require_credential)
    # basic
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()
    if not username:
        errors["username"] = "Username is required."
    elif ":" in username:
        errors["username"] = "Username must not contain ':' (RFC 7617)."
    if require_credential and not password:
        errors["password"] = "Password is required."
    return {"mode": "basic", "username": username, "password": password}


def _build_client_credentials(
    form: Mapping, errors: dict[str, str], require_credential: bool
) -> dict:
    """OAuth2 client-credentials descriptor. clientSecret is the only secret subfield;
    scope/audience are optional and omitted when blank (harness.remote.oauth)."""
    token_url = (form.get("token_url") or "").strip()
    client_id = (form.get("client_id") or "").strip()
    client_secret = (form.get("client_secret") or "").strip()
    scope = (form.get("scope") or "").strip()
    audience = (form.get("audience") or "").strip()

    if not token_url:
        errors["token_url"] = "Token URL is required."
    elif not _valid_url(token_url):
        errors["token_url"] = "Token URL must be a valid http:// or https:// URL."
    if not client_id:
        errors["client_id"] = "Client ID is required."
    if require_credential and not client_secret:
        errors["client_secret"] = "Client secret is required."

    descriptor = {
        "mode": "client-credentials",
        "tokenUrl": token_url,
        "clientId": client_id,
        "clientSecret": client_secret,
    }
    if scope:
        descriptor["scope"] = scope
    if audience:
        descriptor["audience"] = audience
    return descriptor
