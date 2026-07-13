"""Dispatch input/output types for the connector client (contracts/client-api.md)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorSnapshot:
    """Connector config as snapshotted onto a Job (parent FR-023). Built by 012."""

    connector_id: str
    endpoint_url: str
    auth_descriptor: dict  # ciphertext subfields (verbatim from the Job snapshot)
    timeout_seconds: int
    expects_per_row_password: bool


@dataclass(frozen=True)
class UtteranceRow:
    """One row to dispatch. `password` is in-memory only, never persisted (FR-017)."""

    test_id: str
    utterance_text: str
    password: str | None = None


@dataclass(frozen=True)
class ConnectorResult:
    """Outcome of one dispatch: a validated contract or a categorized failure."""

    ok: bool
    contract: dict | None = None
    error_stage: str | None = None  # connector_auth|transport|response|normalization
    error_details: str | None = None
    status_code: int | None = None
