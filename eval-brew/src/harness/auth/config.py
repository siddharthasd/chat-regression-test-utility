"""Auth configuration helpers — no Flask/FastAPI imports (importable anywhere)."""
from __future__ import annotations

import os


def is_auth_enabled() -> bool:
    """Return True when HARNESS_AUTH_ENABLED env var is set to a truthy value."""
    return os.environ.get("HARNESS_AUTH_ENABLED", "true").lower() in {"1", "true", "yes"}


def get_auth_config() -> dict:
    """Return auth configuration from environment variables.

    Raises RuntimeError if required env vars are missing when auth is enabled.
    """
    if not is_auth_enabled():
        return {}

    required = {
        "tenant_id": "HARNESS_AZURE_TENANT_ID",
        "client_id": "HARNESS_AZURE_CLIENT_ID",
        "client_secret": "HARNESS_AZURE_CLIENT_SECRET",
        "secret_key": "HARNESS_SESSION_SECRET",
    }
    cfg: dict[str, str] = {}
    missing = []
    for key, env_var in required.items():
        value = os.environ.get(env_var)
        if not value:
            missing.append(env_var)
        else:
            cfg[key] = value

    if missing:
        raise RuntimeError(
            f"Auth is enabled but the following environment variables are not set: "
            f"{', '.join(missing)}"
        )

    cfg["redirect_uri"] = os.environ.get("HARNESS_REDIRECT_URI", "")
    return cfg
