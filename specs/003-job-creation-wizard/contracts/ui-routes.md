# Contract: Job Creation Wizard UI Routes (Module 9)

**Date**: 2026-06-04
Server-rendered Flask blueprint `wizard`. Entry point for the dashboard's "Create New Job" (FR-021). Consumes 011 (CSV), 007/008 readers (dropdowns + snapshots via 009), 012 (`enqueue_job`).

---

## Routes

### `GET /jobs/new`
Step 1 form (job name + optional description). No Job exists yet.

### `POST /jobs`
Create the Draft. Form: `job_name` (required), `description` (optional). Empty name → re-render Step 1 with error (400). On success: `create_draft(name, description, IdentityContext.current().value)` → `302` to `GET /jobs/<id>/step2`. `created_by` is never a form field (FR-004/020).

### `GET /jobs/<id>` — resume (FR-017)
`302` to `GET /jobs/<id>/step<lowest_incomplete>` (or step5 if complete). Unknown id → 404.

### `GET /jobs/<id>/step1` · `POST /jobs/<id>/step1`
GET: name/description pre-filled. POST: update (draft-guarded), empty name → 400 re-render → else `302` step2.

### `GET /jobs/<id>/step2` · `POST /jobs/<id>/step2`
GET: upload form + (if present) the last summary (utterance count, distinct-testId count) or a pending message. POST: multipart `csv_file` → temp file → `process_upload`. Failure → re-render Step 2 with the per-row `errors` (Next disabled), 400. Success → summary shown; `302` step3. (FR-005/006, SC-004)

### `GET /jobs/<id>/step3` · `POST /jobs/<id>/step3`
GET: dropdown of `connector_reader.list_active()`; empty → affordance linking to `connector_registry.new_connector`, Next disabled (FR-008). POST: `connector_id` required → `set_connector_snapshot`. Then password coordination: if `expects_per_row_password` and store empty → `302` step2 with a flash-style message; else `302` step4. (FR-007/009, SC-005/007)

### `GET /jobs/<id>/step4` · `POST /jobs/<id>/step4`
GET: dropdown of `evaluator_reader.list_active()` (description + dimensions shown); empty → affordance to `evaluator_registry.new_evaluator`, Next disabled. POST: `evaluation_agent_id` required → `set_evaluator_snapshot` → `302` step5. (FR-010/011/012, SC-006/007)

### `GET /jobs/<id>/step5` — review (FR-014/015)
Read-only summary (credentials masked — mode label only). `start_ready` flag drives the Start button: false if any step incomplete, the snapshotted connector/evaluator is archived/deleted, or password coordination fails. Shows the blocking reason.

### `POST /jobs/<id>/start` (FR-016, SC-008/009)
`transition_to_queued(job_id)` in one `get_session()`. On `MissingSnapshotFieldError`/`InactiveRegistrationError`/`InvalidTransitionError` → rolled back (job stays draft) → re-render Step 5 with the error (409). On success → `enqueue_job(job_id)` → `302` to `GET /jobs/<id>/started`.

### `GET /jobs/<id>/started`
Confirmation page (stands in for the 002 dashboard): job name + `queued` status + id. Links back to `/jobs/new`.

---

## Cross-cutting
- **No auth** (FR-020): no login route; the OS identity surfaces via the shared `tester_identity` context processor (010).
- **No secrets rendered**: only `auth_descriptor.mode` appears anywhere (Step 5). Verified by a UI test grepping rendered HTML for a known credential.
- **Atomicity**: every step's write is one `get_session()`; Start rolls back on any failure.
- **`enqueue_job`** is a patchable module global (tests assert the enqueue signal without a live worker).
