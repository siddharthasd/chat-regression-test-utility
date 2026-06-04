# Phase 0 Research: Connector Registry & Management (Module 13)

**Date**: 2026-06-04
**Plan**: `specs/013-connector-registry-management/plan.md`
**Spec**: `specs/013-connector-registry-management/spec.md`

Resolves the plan-level decisions. Built on `foundation` (010+009+006+007+008).

---

## R1: UI Framework & Integration

**Decision**: A Flask **Blueprint** (`connector_registry`) registered in the existing `harness.ui.create_app()` (which already wires `initialize_harness` + the tester-identity context processor). Server-rendered **Jinja** templates under `ui/connector_registry/templates/connector_registry/`. No SPA, no JS framework; "Test connection" posts to a route that returns an HTML fragment (or small JSON) rendered inline.

**Rationale**: `create_app()` documents a blueprint-registration point; a blueprint keeps 013 additive and matches how 002/003/004 will attach. Server-rendered templates fit the single-user localhost tool.

**Alternatives**: a separate Flask app (rejected — breaks the single `harness serve` surface); a JS SPA (rejected — unjustified complexity).

---

## R2: Forms & Validation

**Decision**: Hand-rolled server-side parsing/validation (`request.form` → a `parse_connector_form()` in `forms.py` returning either a validated payload or a list of field errors). No `wtforms`/`flask-wtf`. CSRF is not added in v1 (single-user, no-auth, localhost — parent premise); noted as a future hardening if the UI ever leaves localhost.

**Rationale**: One form with conditional per-mode fields is small enough to validate by hand; avoids two new dependencies + CSRF token plumbing. Validation rules come straight from FR-004/FR-005.

---

## R3: Form ↔ Auth Descriptor Mapping

**Decision**: The form's per-mode fields map to the **canonical descriptor** shape used by `009`'s encryption and `harness.remote.auth` (so no translation drift):

| Mode | Form fields | Descriptor (pre-encryption) |
|---|---|---|
| `none` | — | `{"mode": "none"}` |
| `bearer` | token (secret) | `{"mode": "bearer", "credential": <token>}` |
| `api-key-header` | headerName (clear), headerValue (secret) | `{"mode": "api-key-header", "headerName": ..., "credential": <value>}` |
| `basic` | username (clear), password (secret) | `{"mode": "basic", "username": ..., "password": <pw>}` |

`009`'s `ConnectorRegistrationRepository.create/update` encrypts the `credential`/`password` subfields; `harness.remote.auth.build_auth_headers` consumes the decrypted form. The spec's field names (`token`/`headerValue`) are UI labels; the persisted/canonical keys are `credential`/`password`.

---

## R4: Edit — Credential Preservation vs Replacement (FR-011/012)

**Decision**: Secret fields render as a masked placeholder. The service's `update()` includes `auth_descriptor` in the update payload **only** when the tester used "Replace credential" or changed the mode; otherwise it omits `auth_descriptor` so `009`'s repo leaves the existing ciphertext untouched. Existing ciphertext is never decrypted for display (FR-011).

**Rationale**: `009`'s `update` re-encrypts `auth_descriptor` whenever present; gating on "replace" preserves the stored ciphertext for untouched credentials with no special-casing in the repo.

---

## R5: Auth-Mode Change Discards Credential (FR-006)

**Decision**: When `update()` detects `new_mode != stored_mode`, it requires the new mode's credential fields (validated by `forms.py`) and writes a fresh descriptor — the old ciphertext is dropped by replacement. Save is blocked (validation error) if the new mode's required credential fields are empty.

---

## R6: Hard-Delete Gating (FR-019)

**Decision**: Add `JobRepository.count_by_connector_id(connector_id) -> int` (a `SELECT count(*) FROM job WHERE connector_id = ?`). `service.hard_delete()` calls it; if `> 0` it raises `RegistrationInUseError(connector_id, count)` (new, in `connector_registry`); the route renders the block message naming the count. If `0`, it calls `009`'s `repo.hard_delete`. Ids are never recycled (repo assigns fresh UUIDs; FR-020).

**Rationale**: The Job snapshot stores `connector_id`; counting references is a focused read. Soft-delete (archive) remains the default path.

---

## R7: Test Connection (FR-021–025)

**Decision**: `run_test_connection(endpoint_url, decrypted_descriptor, timeout_seconds, expects_per_row_password) -> TestConnectionResult`. It builds the sample body `{"testId": "test-connection", "utteranceText": "ping"}` (+ `"password": "test"` iff `expects_per_row_password`), the auth header via `harness.remote.auth.build_auth_headers`, and POSTs with `httpx` (timeout). It categorizes the outcome — `unreachable` / `tls_failure` / `timeout` / HTTP status / `auth_decrypt_failed` — and for a 2xx body runs `harness.contract.validate_contract` to report "valid contract" or a brief diagnostic (FR-023). Returns a transient `TestConnectionResult`; **nothing is persisted** (FR-024). The route assembles the decrypted descriptor from the form (plaintext for freshly-entered creds; `009`'s `get_auth_descriptor_decrypted` for an unchanged stored credential).

**Rationale**: Mirrors `007`'s wire protocol and reuses the shared auth + contract-validation pieces; the no-persist, non-blocking contract is explicit in the spec.

---

## R8: Dependencies & New Symbols

**Decision**: **No new runtime dependencies** (Flask + httpx already on `foundation`). New code symbols: `ConnectorRegistryService`, `parse_connector_form`, `run_test_connection`, `TestConnectionResult`, `RegistrationInUseError`, and `JobRepository.count_by_connector_id`. Read API (FR-026) is `007`'s existing `ConnectorRegistryReader` — not re-implemented.

---

*All deferred decisions resolved. Implementation can proceed directly.*
