# Contract: ConnectorRegistryService API

**Module**: `harness.connector_registry.service`
**Stability**: Internal — consumed by the `013` Flask blueprint; framework-agnostic (testable over a `Session`).

---

```python
@dataclass(frozen=True)
class TestConnectionResult:
    ok: bool
    category: str          # valid|invalid_contract|http_error|unreachable|timeout|tls_failure|auth_decrypt_failed
    status_code: int | None = None
    detail: str = ""

class RegistrationInUseError(Exception):
    def __init__(self, connector_id: str, job_count: int) -> None: ...

class ConnectorRegistryService:
    def __init__(self, session: Session) -> None: ...

    def create(self, payload: dict) -> ConnectorRegistration:
        """Validate + build descriptor + repo.create (assigns connectorId, encrypts). FR-003."""

    def update(self, connector_id: str, payload: dict, *, replace_credential: bool) -> ConnectorRegistration:
        """Update in place. Mode change requires fresh creds (FR-006). auth_descriptor is
        re-encrypted only when replace_credential or the mode changed; otherwise the stored
        ciphertext is preserved (FR-011/012)."""

    def archive(self, connector_id: str) -> None      # FR-014
    def restore(self, connector_id: str) -> None       # FR-016

    def hard_delete(self, connector_id: str) -> None:
        """Raises RegistrationInUseError if any historical Job references connector_id (FR-019);
        otherwise repo.hard_delete (FR-018/020)."""

    def count_referencing_jobs(self, connector_id: str) -> int  # JobRepository.count_by_connector_id
```

## `forms.parse_connector_form(form: Mapping) -> tuple[dict | None, dict[str, str]]`

Returns `(payload, errors)`. `payload` is `None` when `errors` is non-empty. Enforces FR-004/FR-005 (required fields, URL syntax, timeout range, per-mode credential presence). Builds the canonical descriptor (`credential`/`password` keys).

## `test_connection.run_test_connection(endpoint_url, decrypted_descriptor, timeout_seconds, expects_per_row_password, *, client=None) -> TestConnectionResult`

Sends the fixed sample body (`{"testId":"test-connection","utteranceText":"ping"}` + `"password":"test"` iff `expects_per_row_password`) with the auth header from `harness.remote.auth.build_auth_headers`; categorizes the outcome; validates a 2xx body via `harness.contract.validate_contract` (FR-021–025). Never persists. `client` injectable for tests.

## Invariants

1. `create`/`update` never store plaintext credentials; secrets are encrypted by `009`'s repo (SC-002).
2. `update` without `replace_credential` and without a mode change preserves the existing ciphertext.
3. `hard_delete` is refused while any Job snapshot references the `connector_id` (SC-006).
4. `run_test_connection` performs no writes and never raises for endpoint failures — it returns a categorized result (SC-008/009).
5. Read access for other modules is `harness.connector.ConnectorRegistryReader` (FR-026), not re-implemented here.
