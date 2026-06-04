# Phase 1 Data Model: Evaluator Registry & Management (Module 14)

**Date**: 2026-06-04
**Plan**: `specs/014-evaluator-registry-management/plan.md`

No new persisted entity — `EvaluationAgentRegistration` lives in `009 FR-001b`. This module's data model is the form↔descriptor mapping (incl. ordered dimensions), the transient test-connection result, and the service operations. Mirrors `013`.

---

## Persisted entity (owned by 009)

`EvaluationAgentRegistration`: `evaluation_agent_id` (immutable, harness-assigned), `display_name`, `description` (**required**), `endpoint_url`, `auth_descriptor` (JSON, secrets encrypted), `timeout_seconds` (default 60), `declared_scoring_dimensions` (ordered `list[str]`), `archived`, `created_at`, `updated_at`, `archived_at?`. `014` reads/writes via `009`'s `EvaluationAgentRegistrationRepository`.

## Form fields → payload (FR-002/005/007)

| Field | Required | Rule |
|---|---|---|
| `display_name` | yes | non-empty |
| `description` | **yes** | non-empty |
| `endpoint_url` | yes | valid `http(s)://` URL |
| `auth_mode` | yes | none/bearer/api-key-header/basic |
| `timeout_seconds` | yes | int, default 60, range 1–600 |
| `dimensions` (textarea) | no (may be empty) | newline-separated; each trimmed; blanks dropped; order preserved; duplicates → warning |
| mode-specific creds | per mode | per `013 FR-005` (bearer token; api-key headerName+value; basic username+password) |

Auth descriptor (pre-encryption): same canonical shape as `013` (`credential`/`password` keys encrypted by `009`).

## `TestConnectionResult` (transient, not persisted)

| Field | Type | Notes |
|---|---|---|
| `ok` | `bool` | True iff 2xx **and** body is a valid EvaluationResult |
| `category` | `str` | `valid` / `invalid_result` / `http_error` / `unreachable` / `timeout` / `auth_decrypt_failed` |
| `status_code` | `int \| None` | when received |
| `detail` | `str` | EvaluationResult problem, body preview, or error message |
| `warning` | `str \| None` | soft warning when emitted dimensions diverge from declared (FR-029) |

## `EvaluatorRegistryService` operations (FR-003/006/019/021/024)

| Method | Behavior |
|---|---|
| `create(payload)` | validate → `repo.create` (assigns id, encrypts) |
| `update(id, payload, *, replace_credential)` | mode-change ⇒ require new creds; include `auth_descriptor` only when replacing/mode-changed; persist dimensions in order |
| `archive(id)` / `restore(id)` | delegate to repo |
| `hard_delete(id)` | `count_by_evaluation_agent_id`>0 ⇒ `RegistrationInUseError`; else `repo.hard_delete` |
| `list_registrations(filter, q)` | active/archived/all + display-name substring; alphabetical |
| `count_referencing_jobs(id)` | `JobRepository.count_by_evaluation_agent_id` |

## New exception

`RegistrationInUseError(evaluation_agent_id, job_count)` — FR-024 hard-delete block.

## Dimension rules (FR-007–011, SC-011)

Trimmed; blanks dropped; **order preserved exactly** on save and read-back; duplicates allowed with a non-blocking warning (downstream de-dups); empty list valid (verdict-only evaluators).

## Immutability

`evaluation_agent_id` immutable (FR-018), never recycled (FR-025). Edits never mutate historical Job snapshots (parent FR-023 — `009`/`012`).
