# Phase 1 Data Model: Connector Registry & Management (Module 13)

**Date**: 2026-06-04
**Plan**: `specs/013-connector-registry-management/plan.md`

No new persisted entity — `ConnectorRegistration` lives in `009 FR-001a`. This module's data model is the form↔descriptor mapping, the transient test-connection result, and the service operations.

---

## Persisted entity (owned by 009)

`ConnectorRegistration`: `connector_id` (immutable, harness-assigned UUID), `display_name`, `description?`, `endpoint_url`, `auth_descriptor` (JSON, secret subfields encrypted), `timeout_seconds` (default 30), `expects_per_row_password` (bool), `archived` (bool), `created_at`, `updated_at`, `archived_at?`. `013` only reads/writes via `009`'s `ConnectorRegistrationRepository`.

## Form fields → descriptor (FR-002/005, R3)

| Field | Required | Rule |
|---|---|---|
| `display_name` | yes | non-empty |
| `description` | no | |
| `endpoint_url` | yes | syntactically valid `http(s)://` URL |
| `auth_mode` | yes | `none`/`bearer`/`api-key-header`/`basic` |
| `timeout_seconds` | yes | int, default 30, range 1–300 |
| `expects_per_row_password` | yes | bool, default false |
| mode-specific creds | per mode | bearer→token; api-key-header→headerName+headerValue; basic→username+password |

Descriptor (pre-encryption): `none`→`{mode}`; `bearer`→`{mode,credential}`; `api-key-header`→`{mode,headerName,credential}`; `basic`→`{mode,username,password}`. (`credential`/`password` encrypted by `009`.)

## `TestConnectionResult` (transient, not persisted)

| Field | Type | Notes |
|---|---|---|
| `ok` | `bool` | True iff 2xx **and** body is a valid contract |
| `category` | `str` | `valid` / `invalid_contract` / `http_error` / `unreachable` / `timeout` / `tls_failure` / `auth_decrypt_failed` |
| `status_code` | `int \| None` | when a response was received |
| `detail` | `str` | truncated body preview or error/diagnostic message |

## `ConnectorRegistryService` operations (FR-003/006/014/016/018/019)

| Method | Behavior |
|---|---|
| `create(payload)` | validate → build descriptor → `repo.create` (assigns id, encrypts) → return registration |
| `update(connector_id, payload, *, replace_credential)` | mode-change ⇒ require new creds (FR-006); include `auth_descriptor` only when replacing/mode-changed (R4); `repo.update`, bump `updated_at` |
| `archive(connector_id)` / `restore(connector_id)` | delegate to `repo.archive`/`repo.restore` (FR-014/016) |
| `hard_delete(connector_id)` | `count_by_connector_id`>0 ⇒ raise `RegistrationInUseError`; else `repo.hard_delete` (FR-019) |
| `count_referencing_jobs(connector_id)` | `JobRepository.count_by_connector_id` |

## New exception

`RegistrationInUseError(connector_id, job_count)` — raised by `hard_delete` when historical Jobs reference the registration (FR-019). Surfaced by the route as a non-destructive block message.

## Versioning / immutability

`connector_id` immutable across edits (FR-013); never recycled after hard-delete (FR-020). Edits never retroactively change a historical Job's snapshot (parent FR-023 — enforced by `009`/`012`, not here).
