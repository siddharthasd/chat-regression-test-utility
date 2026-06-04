# Phase 0 Research: Connector Framework (Module 4)

**Date**: 2026-06-04
**Plan**: `specs/007-connector-framework/plan.md`
**Spec**: `specs/007-connector-framework/spec.md`

Resolves the plan-level decisions the spec deferred (HTTP client, mock service shape, error mapping, credential decryption reuse). Built on the `foundation` branch (010+009+006).

---

## R1: HTTP Client Library

**Decision**: `httpx>=0.27`, a synchronous `httpx.Client` per dispatch with an explicit `timeout=httpx.Timeout(timeout_seconds)`. Client paths are unit-tested with `httpx.MockTransport`, which routes requests to an in-process handler — no socket, fully deterministic.

**Rationale**: FR-004 needs a hard per-request timeout and FR-006 needs to distinguish transport vs. response failures; httpx raises `httpx.TimeoutException` / `httpx.TransportError` for the former and gives `response.status_code` for the latter. `MockTransport` makes the error-mapping table testable without standing up a server.

**Alternatives considered**:
- `requests`: works, but no first-class injectable transport for tests (needs `responses`/`requests-mock` add-ons) and a clunkier timeout tuple. Rejected for testability.
- stdlib `urllib`: awkward timeouts, no clean mock seam. Rejected.

---

## R2: Bundled Mock Connector Service

**Decision**: stdlib `http.server` — a `ThreadingHTTPServer` + `BaseHTTPRequestHandler` bound to `127.0.0.1:<port>` (`:0` for an ephemeral free port in tests). Launchable three ways: `python -m harness.connector.mock`, `harness mock-connector [--port] [--mode]`, or spawned as a child process by tests. Behavior parameterized by `--mode` / `HARNESS_MOCK_MODE`: `ok` (default — deterministic conformant contract reflecting the utterance), `nonconformant` (2xx invalid body), `status500` (non-2xx), `slow` (sleep past timeout).

**Rationale**: FR-021 requires the mock to run in any test with no external dep and no network — stdlib keeps it dependency-free and trivially child-process-spawnable. FR-020's parameterized error modes drive the SC-008/009/010 tests directly.

**Alternatives considered**:
- Flask app: already a dep, but heavier to launch as a standalone child process and overkill for one endpoint. Rejected.
- `pytest-httpserver`: a test-only fixture, not a shippable reference service (FR-019 wants a real bundled mock). Rejected.

---

## R3: errorStage Mapping (FR-006)

**Decision**: Map outcomes to the canonical 9-value enum (reusing `009`'s `ERROR_STAGES` strings):

| Outcome | errorStage |
|---|---|
| credential decryption fails (before send) | `connector_auth` |
| `httpx.TimeoutException` / connect / DNS / TLS error | `connector_transport` |
| HTTP status not 2xx | `connector_response` (capture truncated body in `errorDetails`) |
| 2xx but body not JSON, or `validate_contract` fails | `connector_normalization` |
| 2xx + valid contract | success (no errorStage) |

**Rationale**: Direct restatement of FR-006 + the edge-case table. `connector_normalization` is the `006`-anchored validation stage. Decryption is attempted first so an auth failure never sends a request.

---

## R4: Credential Decryption — Reuse `009`, Don't Re-implement

**Decision**: FR-013/014/016 are **already satisfied by `009`** (`harness.persistence.encryption.encrypt_credential`/`decrypt_credential` + `ConnectorRegistrationRepository` encrypt-on-write/decrypt-on-read). `007` consumes them. At dispatch time the client decrypts the **snapshot's** `connector_auth_descriptor` (verbatim ciphertext copied onto the Job) via a small `_decrypt_descriptor()` helper in `connector/auth.py` that calls `decrypt_credential` on the `credential` / `password` subfields — the same subfield convention `009` uses. On `HarnessKeyMismatchError`, the dispatch returns `connector_auth` (FR-016).

**Rationale**: One encryption/key path for the whole harness (FR-014's machine-local key already lives in `009`). Re-implementing Fernet here would create a second key-handling path and risk divergence. The helper mirrors `009`'s subfield convention rather than importing its private `repositories._auth_descriptor` module.

---

## R5: Auth Header Construction (FR-007a–d)

**Decision**: `build_auth_headers(descriptor: dict) -> dict[str, str]` on a **decrypted** descriptor:
- `none` → `{}` (FR-007a, no header added).
- `bearer` → `{"Authorization": "Bearer <credential>"}`.
- `api-key-header` → `{<headerName>: <credential>}`.
- `basic` → `{"Authorization": "Basic " + base64(f"{username}:{password}")}`.
- unknown mode → raise `ValueError` (FR-008).

**Rationale**: Pure function over the decrypted descriptor — independently unit-testable (FR-007*), no I/O.

---

## R6: Registry Read Facade (FR-009–011)

**Decision**: `ConnectorRegistryReader(session)` wrapping `009`'s `ConnectorRegistrationRepository`:
- `list_active() -> list[ConnectorListEntry]` — minimal tuple `(connector_id, display_name, description, expects_per_row_password)`; excludes archived (delegates to `repo.get_active()`).
- `get(connector_id) -> ConnectorRegistration | None` — full record (raw ciphertext intact).

**Rationale**: FR-009–011 define a stable read surface distinct from `013`'s write surface; both sit on the one `009` table, so the reader is a thin facade. `list_active` returns a lightweight frozen dataclass so the wizard dropdown (`003`) isn't coupled to the ORM row.

---

## R7: Request Body Construction (FR-002 / FR-017)

**Decision**: `{"testId": row.test_id, "utteranceText": row.utterance_text}`; add `"password": row.password` **iff** the snapshot's `expects_per_row_password` is `true`. When false the key is omitted entirely (not `null`, not `""`). The per-row password is forwarded plaintext in the body and **never persisted/encrypted** (FR-017, parent FR-010).

---

## R8: `dispatch_utterance` Signature & Decoupling

**Decision**:
```python
dispatch_utterance(snapshot: ConnectorSnapshot, row: UtteranceRow,
                   *, client: httpx.Client | None = None) -> ConnectorResult
```
`ConnectorSnapshot` is a small frozen dataclass (`endpoint_url`, `auth_descriptor` [ciphertext], `timeout_seconds`, `expects_per_row_password`, `connector_id`) the orchestrator builds from the Job's snapshot columns. `UtteranceRow` carries `test_id`, `utterance_text`, `password | None`. Optional injected `client` enables `MockTransport` tests.

**Rationale**: Decoupling from the ORM/DB makes the client fully unit-testable from plain dataclasses; the orchestrator (`012`) owns reading the Job and the per-job serialization (FR-005).

---

## R9: Dependency Additions

**Decision**: add `httpx>=0.27` to `pyproject.toml` `[project].dependencies`. The mock service is stdlib-only (no dep). No new dev deps.

| Package | Min version | Reason |
|---|---|---|
| `httpx` | `>=0.27` | sync client, per-request timeout, `MockTransport` for tests |

---

*All deferred decisions resolved. Implementation can proceed directly.*
