"""Server-side form parsing + validation for connector registrations (FR-002/004/005).

Maps the UI form fields to the canonical auth descriptor (`credential`/`password`
keys) that 009's encryption and harness.remote.auth consume. No wtforms.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

AUTH_MODES = ("none", "bearer", "api-key-header", "basic", "client-credentials")
TIMEOUT_MIN, TIMEOUT_MAX = 1, 300
_TRUTHY = {"1", "true", "on", "yes"}


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_connector_form(
    form: Mapping, *, require_credential: bool = True
) -> tuple[dict | None, dict[str, str]]:
    """Validate a create/edit form. Returns (payload, errors); payload is None iff errors.

    When `require_credential` is False (editing without replacing the secret), the
    mode-specific credential fields are optional and the descriptor carries no secret.
    """
    errors: dict[str, str] = {}

    display_name = (form.get("display_name") or "").strip()
    if not display_name:
        errors["display_name"] = "Display name is required."

    description = (form.get("description") or "").strip() or None

    endpoint_url = (form.get("endpoint_url") or "").strip()
    if not endpoint_url:
        errors["endpoint_url"] = "Endpoint URL is required."
    elif not _valid_url(endpoint_url):
        errors["endpoint_url"] = "Endpoint URL must be a valid http:// or https:// URL."

    mode = (form.get("auth_mode") or "").strip()
    if mode not in AUTH_MODES:
        errors["auth_mode"] = "Select a valid auth mode."

    raw_timeout = (form.get("timeout_seconds") or "").strip()
    timeout = 30
    try:
        timeout = int(raw_timeout) if raw_timeout else 30
        if not TIMEOUT_MIN <= timeout <= TIMEOUT_MAX:
            errors["timeout_seconds"] = (
                f"Timeout must be between {TIMEOUT_MIN} and {TIMEOUT_MAX} seconds."
            )
    except ValueError:
        errors["timeout_seconds"] = "Timeout must be an integer."

    expects = (form.get("expects_per_row_password") or "").strip().lower() in _TRUTHY
    supports_sse = (form.get("supports_sse") or "").strip().lower() in _TRUTHY

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
        "expects_per_row_password": expects,
        "supports_sse": supports_sse,
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
