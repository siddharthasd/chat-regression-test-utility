"""Machine-local Fernet encryption for authDescriptor credential subfields.

Consumed only by the two registration repositories and ``engine.py``. The
encryption boundary is per-credential-subfield (not the whole descriptor) per
009 FR-008 / research R4. See contracts/encryption-utility-api.md.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from harness.persistence.exceptions import HarnessKeyMismatchError

_KEY_LOCK = threading.Lock()
_CACHED_KEY: bytes | None = None
_KEY_FILENAME = "master.key"


def _key_file_path() -> Path:
    """Resolve the machine-local key file path (research R4 priority order)."""
    override = os.environ.get("HARNESS_KEY_FILE")
    if override:
        return Path(override)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "harness" / _KEY_FILENAME
    return Path.home() / ".harness" / _KEY_FILENAME


def get_or_create_key() -> bytes:
    """Return the Fernet key bytes, creating the key file on first use.

    Priority order:
    1. ``HARNESS_MASTER_KEY`` env var — key bytes supplied directly (no file
       needed; preferred for container/PaaS deployments).
    2. File at ``HARNESS_KEY_FILE`` (or the platform default path) — created
       with mode ``0o600`` via ``O_CREAT | O_EXCL`` on first use. Thread-safe.
    """
    global _CACHED_KEY
    with _KEY_LOCK:
        if _CACHED_KEY is not None:
            return _CACHED_KEY
        env_key = os.environ.get("HARNESS_MASTER_KEY")
        if env_key:
            _CACHED_KEY = env_key.strip().encode("ascii")
            return _CACHED_KEY
        path = _key_file_path()
        if path.exists():
            _CACHED_KEY = path.read_bytes().strip()
            return _CACHED_KEY
        path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        # O_EXCL: fail if another process created it between the check and now.
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        _CACHED_KEY = key
        return _CACHED_KEY


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a single credential string; return URL-safe base64 ciphertext."""
    token = Fernet(get_or_create_key()).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a credential ciphertext string.

    Raises:
        HarnessKeyMismatchError: if the ciphertext cannot be decrypted
            (wrong key, corrupted ciphertext, or key file missing).
    """
    try:
        return Fernet(get_or_create_key()).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise HarnessKeyMismatchError() from exc


def _reset_key_cache_for_tests() -> None:
    """Clear the in-process key cache. Test-only hatch (e.g. key-rotation tests)."""
    global _CACHED_KEY
    with _KEY_LOCK:
        _CACHED_KEY = None


# ---------------------------------------------------------------------------
# Descriptor-level helpers — operate on the three secret subfields of an
# authDescriptor dict. Consumed by the repository layer (_auth_descriptor.py)
# and by the remote auth layer (remote/auth.py). Centralised here so the
# canonical list of secret fields is never duplicated.
# ---------------------------------------------------------------------------

_SECRET_SUBFIELDS: tuple[str, ...] = ("credential", "password", "clientSecret")


def encrypt_descriptor(descriptor: dict) -> dict:
    """Return a copy of *descriptor* with each secret subfield Fernet-encrypted."""
    result = dict(descriptor)
    for key in _SECRET_SUBFIELDS:
        value = result.get(key)
        if value is not None:
            result[key] = encrypt_credential(str(value))
    return result


def decrypt_descriptor(descriptor: dict) -> dict:
    """Return a copy of *descriptor* with each secret subfield decrypted.

    Raises HarnessKeyMismatchError (via decrypt_credential) if any ciphertext
    cannot be decrypted with the current machine-local key.
    """
    result = dict(descriptor)
    for key in _SECRET_SUBFIELDS:
        value = result.get(key)
        if value is not None:
            result[key] = decrypt_credential(value)
    return result
