"""Descriptor-level encrypt/decrypt re-exported from persistence.encryption.

The encryption boundary is per-subfield: only ``credential`` (bearer /
api-key-header), ``password`` (basic), and ``clientSecret`` (client-credentials)
hold ciphertext; ``mode`` / ``headerName`` / ``username`` / ``tokenUrl`` /
``clientId`` / ``scope`` / ``audience`` stay plaintext (009 FR-008, encryption
contract).

The canonical implementations and the list of secret subfields live in
``harness.persistence.encryption``; this module re-exports them so repository
code can import from its own package without crossing layers.
"""

from harness.persistence.encryption import (  # noqa: F401  (public re-exports)
    decrypt_descriptor,
    encrypt_descriptor,
)
