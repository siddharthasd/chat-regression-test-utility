# Phase 1 Data Model: Connector Framework (Module 4)

**Date**: 2026-06-04
**Plan**: `specs/007-connector-framework/plan.md`

`007` adds **no persisted entities** — `ConnectorRegistration` lives in `009`. Its "data model" is the wire-protocol message shapes and the in-memory dispatch input/output types.

---

## Input: `ConnectorSnapshot` (frozen dataclass)

Built by the orchestrator from the Job's snapshot columns (parent FR-023); never read live from the registry at execution time.

| Field | Type | Source (Job snapshot) |
|---|---|---|
| `connector_id` | `str` | `Job.connector_id` |
| `endpoint_url` | `str` | `Job.connector_endpoint_url` |
| `auth_descriptor` | `dict` (ciphertext subfields) | `Job.connector_auth_descriptor` |
| `timeout_seconds` | `int` | `Job.connector_timeout_seconds` |
| `expects_per_row_password` | `bool` | `Job.connector_expects_per_row_password` |

## Input: `UtteranceRow` (frozen dataclass)

| Field | Type | Notes |
|---|---|---|
| `test_id` | `str` | |
| `utterance_text` | `str` | |
| `password` | `str \| None` | in-memory only; forwarded iff `expects_per_row_password` (FR-002/017) |

## Output: `ConnectorResult` (frozen dataclass)

| Field | Type | Notes |
|---|---|---|
| `ok` | `bool` | True iff a 2xx body validated against the contract |
| `contract` | `dict \| None` | the validated Standard Evaluation Contract instance (FR-003) |
| `error_stage` | `str \| None` | one of the 4 connector stages when `ok is False` |
| `error_details` | `str \| None` | actionable detail (timeout msg, truncated body, validation summary) |
| `status_code` | `int \| None` | HTTP status when a response was received |

---

## Wire Protocol (FR-001–003)

**Request** — `POST <endpoint_url>`, `Content-Type: application/json`:
```json
{ "testId": "row-1", "utteranceText": "What is my balance?" }
```
`"password": "..."` is added **iff** `expects_per_row_password` is true; otherwise omitted entirely.

**Success response** — `200`, `Content-Type: application/json`, body = a Standard Evaluation Contract instance (`006`) with `connectorId` populated. Single-shot: one row = one request = one response; no session, no `connect`/`disconnect`, no retry.

---

## Auth Descriptor Shapes (decrypted, FR-007a–d)

```json
{"mode": "none"}
{"mode": "bearer", "credential": "<plaintext after decrypt>"}
{"mode": "api-key-header", "headerName": "X-Api-Key", "credential": "<plaintext>"}
{"mode": "basic", "username": "alice", "password": "<plaintext>"}
```
→ headers: `none` adds nothing; `bearer` → `Authorization: Bearer <cred>`; `api-key-header` → `<headerName>: <cred>`; `basic` → `Authorization: Basic <base64(user:pass)>`.

At rest the `credential`/`password` subfields are Fernet ciphertext (`009`); decryption happens just-in-time and the plaintext is dropped after the request (FR-015).

---

## errorStage Mapping (FR-006) — reuses `009.ERROR_STAGES`

| Condition | `error_stage` |
|---|---|
| decrypt fails before send | `connector_auth` |
| timeout / connect / DNS / TLS | `connector_transport` |
| non-2xx status | `connector_response` |
| 2xx, body not JSON or contract-invalid | `connector_normalization` |

## Registry Read Types (FR-009–011)

- `ConnectorListEntry` (frozen): `connector_id`, `display_name`, `description`, `expects_per_row_password` — for the wizard dropdown.
- `get(connector_id)` returns the full `009` `ConnectorRegistration` ORM record (ciphertext intact).
