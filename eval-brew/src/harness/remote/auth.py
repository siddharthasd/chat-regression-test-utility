"""Auth-header construction (shared, FR-007).

The single source of truth for the five auth modes (``none`` / ``bearer`` /
``api-key-header`` / ``basic`` / ``client-credentials``) used by both the
connector (007) and evaluator (008) HTTP clients.

Descriptor decryption is provided by ``harness.persistence.encryption`` and
re-exported here so callers have a single import point for both concerns.
The ``client-credentials`` token exchange lives in ``remote.oauth``; this
module only builds headers from an already-resolved descriptor.
"""

from __future__ import annotations

import base64

from harness.persistence.encryption import decrypt_descriptor  # noqa: F401 — re-export


def build_auth_headers(descriptor: dict) -> dict[str, str]:
    """Build request auth headers from an already-DECRYPTED, already-RESOLVED descriptor.

    ``client-credentials`` descriptors must be resolved to ``bearer`` first via
    ``remote.oauth.resolve_auth_descriptor`` before calling this function.

    Raises ValueError for any unrecognised mode.
    """
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
