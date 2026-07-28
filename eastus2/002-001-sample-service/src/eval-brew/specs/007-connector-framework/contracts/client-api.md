# Contract: Connector Client API

**Module**: `harness.connector`
**Stability**: Internal-stable — consumed by the orchestrator (`012`) per row.

---

## Public API

```python
@dataclass(frozen=True)
class ConnectorSnapshot:
    connector_id: str
    endpoint_url: str
    auth_descriptor: dict          # ciphertext subfields (verbatim from Job snapshot)
    timeout_seconds: int
    expects_per_row_password: bool

@dataclass(frozen=True)
class UtteranceRow:
    test_id: str
    utterance_text: str
    password: str | None = None

@dataclass(frozen=True)
class ConnectorResult:
    ok: bool
    contract: dict | None = None
    error_stage: str | None = None     # connector_auth|transport|response|normalization
    error_details: str | None = None
    status_code: int | None = None

def dispatch_utterance(
    snapshot: ConnectorSnapshot,
    row: UtteranceRow,
    *,
    client: httpx.Client | None = None,
) -> ConnectorResult:
    """One stateless POST to the connector endpoint; returns a validated contract
    or a categorized failure. Decrypts the snapshot credential just-in-time,
    builds the auth header, enforces timeout_seconds, never retries (FR-001..006).
    `client` is injectable for MockTransport tests."""

def build_auth_headers(descriptor: dict) -> dict[str, str]:
    """Headers for a DECRYPTED descriptor. none→{}; bearer/api-key-header/basic per
    FR-007a-d. Raises ValueError for any other mode (FR-008)."""
```

## `ConnectorRegistryReader(session)` (FR-009–011)

```python
def list_active() -> list[ConnectorListEntry]
    # (connector_id, display_name, description, expects_per_row_password); excludes archived.
def get(connector_id: str) -> ConnectorRegistration | None
    # full 009 record (ciphertext intact).
```

## Invariants

1. `dispatch_utterance` issues **exactly one** HTTP request (or zero, if decryption fails first) and never retries (FR-004/005, SC-006).
2. `ok is True` ⟺ a `200` body parsed as JSON and passed `harness.contract.validate_contract`.
3. Decrypted credential plaintext exists only within `dispatch_utterance`; it is never returned, logged, or stored (FR-015).
4. `build_auth_headers` is pure (no I/O) over an already-decrypted descriptor.
5. `list_active`/`get` return identical data regardless of caller (SC-003).
