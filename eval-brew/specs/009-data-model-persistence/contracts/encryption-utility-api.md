# Contract: Encryption Utility API

**Module**: `harness.persistence.encryption`
**Stability**: Internal-stable — consumed only by the two registration repositories and `engine.py`.

This module manages the machine-local Fernet symmetric key and exposes encrypt/decrypt for `authDescriptor` credential subfields.

---

## Public API

```python
def encrypt_credential(plaintext: str) -> str
    """Encrypt a single credential string.

    Loads (or generates) the machine-local Fernet key, encrypts `plaintext`,
    and returns a URL-safe-base64-encoded ciphertext string suitable for
    storage in a SQLite TEXT column (inside a JSON blob).

    Side effects: may create the key file on first call (see key-file semantics).
    Thread-safe: key loading uses a module-level lock.
    """

def decrypt_credential(ciphertext: str) -> str
    """Decrypt a single credential ciphertext string.

    Raises:
        HarnessKeyMismatchError: if the ciphertext cannot be decrypted
            (wrong key, corrupted ciphertext, or key file missing).
            Message: "machine-local key missing or wrong"
    """

def get_or_create_key() -> bytes
    """Return the Fernet key bytes, creating the key file if it doesn't exist.

    Key file location priority:
    1. `HARNESS_KEY_FILE` environment variable (absolute path).
    2. `%LOCALAPPDATA%\\harness\\master.key` on Windows.
    3. `~/.harness/master.key` on macOS/Linux.

    File is created with mode 0o600 (owner-read-only) using os.O_CREAT|os.O_EXCL
    to prevent races. Parent directories are created if absent.

    Thread-safe: protected by a module-level threading.Lock.
    """
```

---

## Credential Subfield Convention

An `authDescriptor` dict has the following structure depending on `mode`:

```json
// mode = "none"
{"mode": "none"}

// mode = "bearer"
{"mode": "bearer", "credential": "<FERNET_CIPHERTEXT>"}

// mode = "api-key-header"
{"mode": "api-key-header", "headerName": "X-Api-Key", "credential": "<FERNET_CIPHERTEXT>"}

// mode = "basic"
{"mode": "basic", "username": "alice", "password": "<FERNET_CIPHERTEXT>"}
```

Only the `credential` and `password` subfields contain ciphertext. `mode`, `headerName`, and `username` are always plaintext (non-secret). Repositories encrypt these before writing the JSON column and decrypt them only in `get_auth_descriptor_decrypted()`.

---

## Key File Semantics

- Key is a 32-byte random value encoded as a 44-character URL-safe-base64 string (Fernet key format).
- On first `encrypt_credential()` or `get_or_create_key()` call: key is generated via `Fernet.generate_key()`, written to the key file with `0o600` permissions.
- On subsequent calls: key is read from the file.
- Key is cached in-process after first load (module-level variable); cleared only on process exit.
- If the key file is deleted or the DB is moved to a different machine: `decrypt_credential()` raises `HarnessKeyMismatchError` for every attempt. The DB is still readable; only encrypted credential fields fail.

---

## Invariants

1. `decrypt_credential(encrypt_credential(s)) == s` for any non-empty string `s`.
2. `encrypt_credential(s)` never returns the same ciphertext twice for the same input (Fernet includes a random IV).
3. `encrypt_credential` and `decrypt_credential` never log or print the plaintext value.
4. The key file permissions are `0o600` on creation; the module does NOT re-set permissions on read (the OS may have changed them).
5. `HarnessKeyMismatchError` message is always exactly: `"machine-local key missing or wrong"` (per spec edge case and `009 FR-003`'s `errorStage = "connector_auth"` / `"evaluator_auth"` paths).
