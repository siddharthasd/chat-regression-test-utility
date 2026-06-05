"""Helpers to encrypt/decrypt the secret subfields of an authDescriptor.

The encryption boundary is per-subfield: only ``credential`` (bearer /
api-key-header), ``password`` (basic), and ``clientSecret`` (client-credentials)
hold ciphertext; ``mode`` / ``headerName`` / ``username`` / ``tokenUrl`` /
``clientId`` / ``scope`` / ``audience`` stay plaintext (009 FR-008, encryption
contract).
"""

from __future__ import annotations

from harness.persistence.encryption import decrypt_credential, encrypt_credential

_SECRET_SUBFIELDS = ("credential", "password", "clientSecret")


def encrypt_descriptor(descriptor: dict) -> dict:
    """Return a copy of ``descriptor`` with secret subfields Fernet-encrypted."""
    result = dict(descriptor)
    for key in _SECRET_SUBFIELDS:
        value = result.get(key)
        if value is not None:
            result[key] = encrypt_credential(str(value))
    return result


def decrypt_descriptor(descriptor: dict) -> dict:
    """Return a copy of ``descriptor`` with secret subfields decrypted."""
    result = dict(descriptor)
    for key in _SECRET_SUBFIELDS:
        value = result.get(key)
        if value is not None:
            result[key] = decrypt_credential(value)
    return result
