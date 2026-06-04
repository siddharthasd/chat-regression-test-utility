# Phase 0 Research: Job Creation & Configuration Wizard (Module 9)

**Date**: 2026-06-04 | **Plan**: `specs/003-job-creation-wizard/plan.md`

Built on `foundation`. Server-rendered Flask, no new deps. Resolves the plan-level decisions.

---

## R1: Wizard state model (FR-003/017, no stored cursor)
**Decision**: The **Draft Job row is the wizard state** — there is no separate session/cursor entity. The current step is *derived* each request from the "lowest-numbered incomplete step" predicate (Key Entities: "the current-step pointer ... does not need to be stored separately"). Auto-save = each step's POST writes that step's data to the Job before redirecting.
**Rationale**: matches the spec exactly, avoids session state, makes resume trivially correct (open `/jobs/<id>` → compute cursor → redirect). Survives process restart (the Job is in SQLite).

## R2: Step-completion predicates (FR-017, SC-002/003)
**Decision**: pure functions over the Job + the two readers (see plan §predicates). S2 keys on `total_utterance_count` (set by 011). S3/S4 require the snapshot id **and** that `reader.get(id)` resolves to a non-archived registration (so an archived/deleted selection re-opens the step — US2 sc3/4, SC-010).
**Rationale**: deriving "active" at read time via the reader is the only way to honor "must re-select if archived since" without storing liveness on the Job.

## R3: Per-row-password coordination (FR-005, reshape, edge cases)
**Decision**: Step 2 uploads with `password` optional (connector not yet chosen → snapshot flag unset → 011 treats it optional, stages nothing). On Step 3 Next, if the chosen connector `expects_per_row_password` and `password_store.job_has_entries(job_id)` is false → bounce to Step 2 with a message; the re-upload (now with the snapshot flag true) makes 011 enforce + stage. Step 5 Start gate re-checks the same.
**Rationale**: **011 deliberately does not retain the CSV file**, so silent re-validation is impossible — re-validation = re-upload. This is the spec's explicitly plan-level choice (US3 sc3, US4 sc1, the "password column missing" edge case). 011 stays the single validation authority.
**Alternatives**: retaining the CSV to silently re-run (violates `010 Q2`/`011 FR-017` no-retention) — rejected.

## R4: CSV file handling (Step 2)
**Decision**: save the Flask `FileStorage` to a `tempfile.NamedTemporaryFile(delete=False)` path, call `process_upload(job_id, tmp_path, filename=secure_filename(name))`, `os.unlink` in `finally`. Wizard persists nothing itself.
**Rationale**: `process_upload` takes a filesystem path + does the size gate via `stat` before reading; a temp file is the clean bridge from an HTTP multipart upload. Cleanup honors no-retention.

## R5: Snapshot copy (FR-009/012/018, SC-011)
**Decision**: pass the full ORM registration from `reader.get(id)` to `JobRepository.set_connector_snapshot` / `set_evaluator_snapshot`, which copy all fields incl. the encrypted `auth_descriptor` ciphertext verbatim. Re-selecting overwrites the whole snapshot. No re-encryption in the wizard.
**Rationale**: 009's setters are the snapshot authority (draft-guarded, immutable past draft); copying ciphertext verbatim satisfies "the wizard does NOT re-encrypt" (FR-009) and byte-equality (SC-011).

## R6: Empty-registry affordance (FR-008/011, US5, SC-007)
**Decision**: when `list_active()` is empty, the step template hides the dropdown and renders a prominent link to the relevant registry UI (`url_for('connector_registry.new_connector')` / `evaluator_registry.new_connector`-equivalent) with Next disabled. The Draft is untouched, so the round-trip preserves it (resume reopens at the same step).
**Rationale**: direct `url_for` to the existing 013/014 blueprints (already mounted) is the concrete navigation target the spec asks for.

## R7: Start + rollback (FR-016, SC-008/009)
**Decision**: `transition_to_queued(job_id)` inside `get_session()` is the atomic gate — 009 already validates draft status, connector/evaluator presence, and active-registration liveness, raising on violation (rolled back → job stays draft → re-render Step 5 with the error). On success, call `enqueue_job` then PRG-redirect to a confirmation page.
**Rationale**: reuses 009's transition guard as the FR-015/016 enforcement point rather than re-implementing the checks in the wizard; rollback is automatic via the session context manager.

## R8: enqueue testability (SC-008)
**Decision**: import `from harness.orchestrator import enqueue_job` as a module global in `routes.py` and call it by name, so tests can `monkeypatch.setattr("harness.ui.wizard.routes.enqueue_job", spy)`. The test asserts the spy was called for the job id + the job is `queued` with `started_at` set — without spawning a real worker thread (which would immediately drive the job to running/completed against an unreachable snapshot endpoint).
**Rationale**: keeps the SC-008 "engine received an enqueue signal" assertion deterministic; production still gets the real async start.

---

*All decisions resolved. Implementation can proceed.*
