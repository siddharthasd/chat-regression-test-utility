"""Auth-header construction + just-in-time credential decryption (FR-007).

Reuses 009's machine-local encryption. NOTE: this duplicates
``harness.connector.auth`` (007) — 008 is a sibling branch and cannot import
``harness.connector``. Extract a shared helper when 007+008 are integrated.
"""

from __future__ import annotations

import base64

from harness.persistence.encryption import decrypt_credential

_SECRET_SUBFIELDS = ("credential", "password")


def _decrypt_descriptor(descriptor: dict) -> dict:
    """Return a copy of `descriptor` with secret subfields decrypted in memory.

    Raises HarnessKeyMismatchError (from 009) if a ciphertext can't be decrypted.
    """
    result = dict(descriptor)
    for key in _SECRET_SUBFIELDS:
        value = result.get(key)
        if value is not None:
            result[key] = decrypt_credential(value)
    return result


def build_auth_headers(descriptor: dict) -> dict[str, str]:
    """Build auth headers from an already-DECRYPTED descriptor (FR-007; identical to 007)."""
    mode = descriptor.get("mode")
    if mode == "none":
        return {}
    if mode == "bearer":
        return {"Authorization": f"Bearer {descriptor['credential']}"}
    if mode == "api-key-header":
        return {descriptor["headerName"]: descriptor["credential"]}
    if mode == "basic":
        raw = f"{descriptor['username']}:{descriptor['password']}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
    raise ValueError(f"unsupported auth mode: {mode!r}")
