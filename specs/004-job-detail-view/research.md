# Phase 0 Research: Job Detail & Traceability View (Module 13)

**Date**: 2026-06-04 | **Plan**: `specs/004-job-detail-view/plan.md`

Built on `foundation`. Server-rendered Flask + thin polling JS, no new deps.

---

## R1: Route ownership (FR-001)
**Decision**: own `GET /jobs/<id>/detail` — the literal href the dashboard (002) already renders. Mutations/aux under the same prefix: `POST /jobs/<id>/cancel`, `POST /jobs/<id>/delete`, `GET /jobs/<id>/download.csv`, `GET /jobs/<id>/detail.json`.
**Rationale**: closes the dashboard→detail loop with the exact path 002 emitted. Distinct from the wizard's `GET /jobs/<id>` (resume) and `POST /jobs/<id>/start`.

## R2: Row + result join (FR-007/008)
**Decision**: `UtteranceRepository.get_by_job_ordered(job_id)` and read `utterance.evaluation_result` (009's one-to-one relationship) — no manual join. Rows with no result yet (queued in a running job) have `evaluation_result is None` → "awaiting" cells.
**Rationale**: the ORM relationship gives ordered rows + their results in one pass; matches the incremental-population model (US5).

## R3: Secret masking (FR-005, SC-003)
**Decision**: `mask_descriptor(d)` copies the stored `auth_descriptor` and replaces the `credential`/`password` subfields with `••••••••` if present, leaving `mode`/`headerName`/`username` (stored cleartext). **Never decrypt.** Jinja autoescape stays on.
**Rationale**: the job snapshot stores the *encrypted* descriptor; the detail view must neither decrypt nor reveal. The secret subfields are exactly `harness.remote.auth._SECRET_SUBFIELDS`. This is what the credential-masking XFAILs assert.

## R4: Ordered scores + annotations (FR-007a/b/c)
**Decision**: render `evaluation_scores` as a structured list ordered by the Job's snapshotted `evaluator_declared_scoring_dimensions`: for each declared dim emit its `{score, reasoning}` (or "—"/"awaiting"), then append any emitted entries whose `parameter_name` is NOT declared (the unexpected ones). A row whose `harness_annotations.unexpected_score_dimensions` is non-empty gets a visible indicator (FR-007c). The harness owns the HTML (autoescaped) — never inject evaluator HTML (FR-007a XSS-safe).
**Rationale**: declared-dimension ordering makes the column stable before/across rows (FR-007b); the annotation indicator surfaces 008's soft-warning.

## R5: Filters / sort / search (FR-011/012/013/014)
**Decision**: server-side via query params — `verdict` (multi), `error_only` (toggle → only `errorStatus == failed`), `test_id` (multi), `q` (substring over utterance_text OR chatbot_response_text only). AND-combined. Sort any column **except scores** (FR-011, header omits the affordance); verdict sorts by fixed order `fail` > `warn` > `pass`. A "Visible: N of M" indicator shows when any filter/search is active (FR-014a).
**Rationale**: server-side is fully testable and meets the 200 ms SC-010 budget for 1,000 rows; the scores-not-sortable rule is honored by simply not emitting a sort link on that header.

## R6: Reconstructed CSV (FR-006/006a, SC-009)
**Decision**: `reconstruct_csv(job, utterances)` builds a CSV from persisted Utterances — header `utteranceText,testId` + any `extra_metadata` keys (original order), **no password column** (parent FR-010). Filename `<base>-reconstructed.csv`; when the job is non-terminal, also `-partial` + an inline `# job <status>, N rows at download` comment line. Served as `text/csv` attachment.
**Rationale**: the verbatim upload isn't retained (011 FR-017) — reconstruct from rows; the partial markers satisfy the non-terminal snapshot-at-click rule.

## R7: Live updates + delete-elsewhere (FR-015/016/020)
**Decision**: `GET /jobs/<id>/detail.json` → `{status, status_label, badge_class, total, processed, failed, row_count, terminal}`; `404` when the job no longer exists. The page polls every 3 s: patch the panel badge + counters; if `row_count` increased, `location.reload()` (query params preserved) to pull new server-rendered rows; on `404`, redirect to `/` with a notice; stop polling once `terminal`.
**Rationale**: polling needs no deps and matches 002; reload-on-growth keeps row rendering server-side (one source of truth) while meeting the ≤5 s appear-without-refresh bound. The 404 path implements FR-020.

## R8: Cancel / Delete gating (FR-018/019, SC-006/007)
**Decision**: controls are shown strictly by status — Cancel iff {queued, running}, Delete iff {draft, failed, cancelled}. Both POSTs re-read in-txn: cancel calls `transition_to_cancelling` (catches `InvalidTransitionError` → 409 race message); delete re-checks membership then `delete` (cascade) → redirect to dashboard.
**Rationale**: reuses 009's transition guard + cascade delete; re-check at execute handles the background-terminal race (FR-018 sc5).

## R9: XSS safety (FR-007a)
**Decision**: render all evaluator-emitted strings (scores `reasoning`, raw response, etc.) through normal Jinja autoescaping; never `|safe` on evaluator data. Large JSON artifacts render inside `<pre>` (text), with a copy button.
**Rationale**: the evaluator is an external service; its output is untrusted. Autoescape is the harness-owns-the-rendering guarantee.

---

*All decisions resolved. Implementation can proceed.*
