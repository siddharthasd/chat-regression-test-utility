"""Connector Framework (Module 4): wire-protocol HTTP client + registry read.

Per-row dispatch is one stateless POST; the orchestrator (012) owns the job loop.
Reuses 009 (registry + encryption) and 006 (`validate_contract`)::

    from harness.connector import dispatch_utterance, ConnectorSnapshot, UtteranceRow
    result = dispatch_utterance(snapshot, row)
"""

from __future__ import annotations

from harness.connector.auth import build_auth_headers
from harness.connector.client import dispatch_utterance
from harness.connector.registry import ConnectorListEntry, ConnectorRegistryReader
from harness.connector.result import ConnectorResult, ConnectorSnapshot, UtteranceRow

__all__ = [
    "ConnectorListEntry",
    "ConnectorRegistryReader",
    "ConnectorResult",
    "ConnectorSnapshot",
    "UtteranceRow",
    "build_auth_headers",
    "dispatch_utterance",
]
