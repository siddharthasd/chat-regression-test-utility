# Implementation Plan: Job Creation & Configuration Wizard (Module 9)

**Branch**: `003-job-creation-wizard` | **Date**: 2026-06-04 | **Spec**: `specs/003-job-creation-wizard/spec.md`
**Base**: `foundation` (006/007/008/009/010/011/012/013/014, tip `e5b889b`, 313 passed / 7 xfailed / ruff clean)

## Summary

A five-step server-rendered Flask wizard that turns tester input into a `queued` Job. It is the surface that finally ties the backend together: **Step 2 calls `csv_upload.process_upload` (011)**, Steps 3/4 snapshot registrations via 009, and **Start calls `orchestrator.enqueue_job` (012)**. No new persistent state — the Draft Job *is* the wizard state; the current step is derived as "lowest-numbered incomplete step" (no stored cursor). Step 3/4 are read-only dropdowns over the 007/008 reader APIs (per the reshape — no per-job config forms, no per-job name override, no wizard-side Test Connection, no contract-version gate).

## Technical Context

**Language**: Python 3.11+ / Flask (matches 013/014 UI). **Storage**: 009 via `JobRepository`, `get_session`. **Templating**: Jinja, standalone `<!doctype html>` templates (no base layout — matches existing registry UIs). **Testing**: pytest + Flask `test_client()` + per-test `engine.init_db(tmp)` isolation + `password_store._reset_for_tests()`. **No new dependencies.**

**Reuse (no duplication)**:
- 009 `JobRepository`: `create_draft(name, description, created_by)`, `get`, `set_connector_snapshot(job_id, registration)`, `set_evaluator_snapshot(job_id, registration)`, `set_csv_metadata` (via 011), `transition_to_queued(job_id)` (draft-guarded; validates connector/evaluator present + active; sets `started_at`; FR-016/SC-008/SC-009 enforcement lives here).
- 007 `ConnectorRegistryReader.list_active()` (Step 3 dropdown) + `.get(id)` (full ORM registration for the snapshot + active/archived check).
- 008 `EvaluatorRegistryReader.list_active()` (Step 4 dropdown, carries `description` + `declared_scoring_dimensions`) + `.get(id)`.
- 011 `csv_upload.process_upload(job_id, file_path, filename=...)` (Step 2).
- 012 `orchestrator.enqueue_job(job_id)` (Start).
- 010 `IdentityContext.current().value` → `Job.createdBy` (FR-004); `harness.password_store.job_has_entries` (per-row-password coordination, see below).

## Source layout (new)

```
src/harness/ui/wizard/__init__.py              # exports bp
src/harness/ui/wizard/routes.py                # the 5-step blueprint + start + resume
src/harness/ui/wizard/steps.py                 # step-completion predicates + lowest-incomplete-step resolver
src/harness/ui/wizard/templates/wizard/step1.html  # create job (name/description)
src/harness/ui/wizard/templates/wizard/step2.html  # CSV upload + summary/errors
src/harness/ui/wizard/templates/wizard/step3.html  # connector dropdown / empty-state
src/harness/ui/wizard/templates/wizard/step4.html  # evaluator dropdown / empty-state
src/harness/ui/wizard/templates/wizard/step5.html  # review + Start
src/harness/ui/wizard/templates/wizard/started.html # post-Start confirmation (stands in for 002 dashboard)
tests/integration/test_wizard_ui.py
```
**Edits**: `src/harness/ui/__init__.py` — register `wizard_bp`. `pyproject.toml` — add `"harness.ui.wizard" = ["templates/wizard/*.html"]` to `[tool.setuptools.package-data]`.

## Routes (contract — see contracts/ui-routes.md)

| Method + path | Purpose |
|---|---|
| `GET /jobs/new` | Step 1 form (no job yet) |
| `POST /jobs` | create Draft (name required, `created_by` from identity) → redirect Step 2 (FR-004) |
| `GET /jobs/<id>` | resume → redirect to lowest-incomplete step (FR-017) |
| `GET/POST /jobs/<id>/step1` | edit name/description |
| `GET/POST /jobs/<id>/step2` | upload CSV → `process_upload`; show summary or per-row errors (FR-005/006) |
| `GET/POST /jobs/<id>/step3` | connector dropdown / empty-state; snapshot on Next (FR-007/008/009) |
| `GET/POST /jobs/<id>/step4` | evaluator dropdown / empty-state; snapshot on Next (FR-010/011/012) |
| `GET /jobs/<id>/step5` | read-only review; Start enabled iff complete + both active + (password coord) (FR-014/015) |
| `POST /jobs/<id>/start` | `transition_to_queued` + `enqueue_job` → redirect confirmation (FR-016) |
| `GET /jobs/<id>/started` | confirmation page (stands in for the 002 dashboard) |

## Step-completion predicates (steps.py — derives the resume cursor, FR-017)

- **S1**: `job.job_name` present (always true once the Job exists).
- **S2**: `job.total_utterance_count` set (CSV uploaded+validated via 011).
- **S3**: `job.connector_id` set **and** `reader.get(connector_id)` is non-None and not archived.
- **S4**: `job.evaluation_agent_id` set **and** evaluator `get(...)` non-None and not archived.
- **S5** (Start-ready): S1–S4 **and** the per-row-password coordination holds (below).
Resume opens at the lowest step whose predicate is false (or Step 5 if all hold).

## Per-row-password coordination (the reshape's plan-level choice; FR-005, US3 sc3, edge cases)

Because **011 does not retain the CSV file**, step-2 cannot be silently re-validated later — re-validation means re-upload. Chosen UX:
1. At **Step 2**, the connector is not yet selected, so the Job snapshot's `connector_expects_per_row_password` is unset → `process_upload` treats `password` as **optional** and stages nothing.
2. On **Step 3 Next**, after snapshotting the connector, if `expects_per_row_password` is `true` **and** `not password_store.job_has_entries(job_id)`, the wizard redirects back to **Step 2** with an actionable message ("the selected connector requires a per-row `password` column — please re-upload"). Re-upload now runs `process_upload` with the snapshot flag `true`, so 011 enforces the column + stages the store.
3. The **Step 5 Start gate** re-checks: if the snapshotted connector `expects_per_row_password` and the store has no entries, Start is disabled with the same message.

This keeps 011 the single validation authority and never silently accepts a password-less CSV for a password-requiring connector.

## CSV file handling (Step 2)

Flask `FileStorage` → save to a `tempfile` path → `process_upload(job_id, tmp_path, filename=secure_filename(upload.filename))` → `os.unlink` the temp in a `finally`. The wizard retains nothing (honors `010 Q2` / `011 FR-017` — only the basename is persisted, by 011).

## Snapshot semantics (FR-009/012/018, SC-011)

`set_connector_snapshot` / `set_evaluator_snapshot` overwrite **all** connector_*/evaluator_* columns from the chosen registration (ciphertext copied verbatim — the wizard never re-encrypts). Re-selecting a different registration on Back replaces the whole snapshot. Draft-guarded by 009. Snapshot is immutable to later registration edits (009 enforces; SC-011).

## Start + rollback (FR-016, SC-008/009)

`POST /start`: in one `get_session()`, `transition_to_queued(job_id)` (raises `MissingSnapshotFieldError`/`InactiveRegistrationError`/`InvalidTransitionError` → rolled back, job stays draft, re-render Step 5 with the error). On success, `enqueue_job(job_id)` (async daemon worker) then redirect to the confirmation page. `enqueue_job` is imported as a module global so tests can monkeypatch it to a spy (asserting the enqueue signal without spawning a real worker).

## Constitution Check
Harness premises only (single-user, no auth — FR-020: no login; identity is OS-derived + auto-stamped, not tester-editable). No new deps. Passwords never rendered (Step 5 masks auth; only mode label shown). Gate: **PASS** (pre/post design).

## Phase 0 / 1 outputs
- `research.md` — R1–R8 (wizard state model, step resolver, password coordination, CSV temp-file handling, snapshot copy, empty-registry affordance, Start/rollback, enqueue testability).
- `data-model.md` — Draft Job field population per step + completion predicates + view projections.
- `contracts/ui-routes.md` — the route table + request/response + gating.
- `quickstart.md` — end-to-end click-through + resume.
- CLAUDE.md SPECKIT marker → `specs/003-job-creation-wizard/plan.md`.
