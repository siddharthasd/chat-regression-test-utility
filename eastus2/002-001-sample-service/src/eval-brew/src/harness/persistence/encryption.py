"""Credential pass-through shim.

Encryption removed: credentials are stored as plaintext in the database.
These functions are identity pass-throughs kept for import compatibility
while callers are incrementally cleaned up.
"""

from __future__ import annotations


def encrypt_credential(plaintext: str) -> str:
    return plaintext


def decrypt_credential(ciphertext: str) -> str:
    return ciphertext


def encrypt_descriptor(descriptor: dict) -> dict:
    return dict(descriptor)


def decrypt_descriptor(descriptor: dict) -> dict:
    return dict(descriptor)
