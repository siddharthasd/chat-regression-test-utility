"""Shared form-to-descriptor helper for connector and evaluator registry routes.

Both registry routes need to reconstruct a (decrypted) auth descriptor from
form values for the in-form "Test connection" button.  The logic is identical
across the two registries so it lives here once.
"""

from __future__ import annotations

from collections.abc import Mapping


def descriptor_from_form(form: Mapping, mode: str) -> tuple[dict, bool]:
    """Build a decrypted auth descriptor from submitted form values.

    Returns ``(descriptor, needs_stored)`` where ``needs_stored`` is True when
    the secret was not re-entered (e.g. editing without replacing the credential)
    and the caller should fetch the stored, decrypted descriptor instead.
    """
    if mode == "bearer":
        token = (form.get("token") or "").strip()
        return {"mode": "bearer", "credential": token}, not token
    if mode == "api-key-header":
        value = (form.get("header_value") or "").strip()
        return {
            "mode": "api-key-header",
            "headerName": (form.get("header_name") or "").strip(),
            "credential": value,
        }, not value
    if mode == "basic":
        password = (form.get("password") or "").strip()
        return {
            "mode": "basic",
            "username": (form.get("username") or "").strip(),
            "password": password,
        }, not password
    if mode == "client-credentials":
        secret = (form.get("client_secret") or "").strip()
        descriptor: dict = {
            "mode": "client-credentials",
            "tokenUrl": (form.get("token_url") or "").strip(),
            "clientId": (form.get("client_id") or "").strip(),
            "clientSecret": secret,
        }
        scope = (form.get("scope") or "").strip()
        audience = (form.get("audience") or "").strip()
        if scope:
            descriptor["scope"] = scope
        if audience:
            descriptor["audience"] = audience
        return descriptor, not secret
    return {"mode": "none"}, False
