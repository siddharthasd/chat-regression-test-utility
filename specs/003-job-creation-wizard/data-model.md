# Phase 1 Data Model: Job Creation & Configuration Wizard (Module 9)

**Date**: 2026-06-04 | **Plan**: `specs/003-job-creation-wizard/plan.md`

The wizard owns **no new entity** — it populates 009's `Job` (a `draft` row) step-by-step and reads the 007/008 registries. The Draft Job *is* the wizard state.

---

## 1. Draft Job field population by step

| Step | Job fields written | Via |
|---|---|---|
| 1 (create) | `job_name`, `description`, `created_at`, `created_by`, `status="draft"` | `JobRepository.create_draft(name, description, created_by)` |
| 1 (edit) | `job_name`, `description` | direct on the draft row (draft-guarded) |
| 2 (CSV) | `total_utterance_count`, `source_csv_filename` + N `Utterance` rows (+ password store) | `csv_upload.process_upload` (011) |
| 3 (connector) | `connector_id/name/endpoint_url/auth_descriptor/timeout_seconds/expects_per_row_password` | `JobRepository.set_connector_snapshot(job_id, registration)` |
| 4 (evaluator) | `evaluation_agent_id/name/endpoint_url/auth_descriptor/timeout_seconds/declared_scoring_dimensions` | `JobRepository.set_evaluator_snapshot(job_id, registration)` |
| 5 (start) | `status="queued"`, `started_at` | `JobRepository.transition_to_queued(job_id)` |

`created_by` = `IdentityContext.current().value` (OS-derived; never in a form — FR-004/020). `auth_descriptor` ciphertext is copied verbatim from the registration (FR-009/012; no re-encryption). Passwords never persist (011 FR-014).

## 2. Step-completion predicates (resume cursor — FR-017)

| Step | Complete when |
|---|---|
| S1 | `job.job_name` truthy |
| S2 | `job.total_utterance_count is not None` |
| S3 | `job.connector_id` set AND `connector_reader.get(id)` non-None and `not archived` |
| S4 | `job.evaluation_agent_id` set AND `evaluator_reader.get(id)` non-None and `not archived` |
| S5 (start-ready) | S1–S4 AND password coordination holds (below) |

`lowest_incomplete_step(job)` → first step whose predicate is false, else 5. `GET /jobs/<id>` redirects there.

## 3. Per-row-password coordination state

| Condition | Effect |
|---|---|
| snapshot `expects_per_row_password` false/unset | nothing required; store unused for this job |
| `expects_per_row_password` true AND `password_store.job_has_entries(job_id)` | OK (CSV staged passwords) |
| `expects_per_row_password` true AND store empty | Step 3 Next bounces to Step 2; Step 5 Start disabled — re-upload required |

## 4. Read projections (templates)

- **Step 3 dropdown**: `ConnectorListEntry(connector_id, display_name, description, expects_per_row_password)` from `list_active()`; label = `display_name` + short `connector_id` tail for disambiguation.
- **Step 4 dropdown**: `EvaluatorListEntry(evaluation_agent_id, display_name, description, declared_scoring_dimensions)` from `list_active()`; description + dimensions shown alongside (FR-010).
- **Step 5 review** (FR-014, all read-only, credentials masked): job name/description; CSV summary (utterance count, distinct-testId count — recomputed from `Utterance` rows); connector name + truncated endpoint + auth-mode label + `expects_per_row_password`; evaluator name + truncated endpoint + auth-mode label + declared dimensions. **No plaintext credential ever rendered** (only `auth_descriptor.mode`).

## 5. Validation / gating rules → requirement

| Rule | FR / SC |
|---|---|
| Step 1 name non-empty | FR-004 |
| Step 2 Next disabled until 011 validation passes | FR-005, SC-004 |
| Step 3/4 Next disabled until a registration selected | FR-007/010, SC-005/006 |
| Empty registry → affordance + Next disabled | FR-008/011, SC-007 |
| Start disabled if incomplete / archived selection / password-coord fails | FR-015, SC-010 |
| Start atomic; rollback leaves draft intact | FR-016, SC-008/009 |
| Snapshot byte-equal at snapshot moment | SC-011 |
