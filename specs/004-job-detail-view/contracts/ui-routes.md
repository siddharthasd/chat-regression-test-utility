# Contract: Job Detail View UI Routes (Module 13)

**Date**: 2026-06-04
Server-rendered Flask blueprint `detail`. The dashboard's row-click target. Consumes 009 only (Job snapshot is the source of truth; registries not read).

---

## Routes

### `GET /jobs/<id>/detail` (FR-001/002/007)
Metadata panel + results table. Query params (optional): `verdict` (repeatable), `error_only` (`1`), `test_id` (repeatable), `q`, `sort`, `dir`. Unknown id → 404. Secrets masked (FR-005). Counts are job-level regardless of filters (FR-003). "Visible: N of M" when filtered (FR-014a). Each row expandable (full trace, FR-008) with copy-to-clipboard for JSON artifacts (FR-009). Scores column has no sort affordance (FR-011). Cancel/Delete controls shown per status gate (FR-018/019).

### `GET /jobs/<id>/detail.json` (FR-015/016/020)
`200 {status, status_label, badge_class, total, processed, failed, row_count, terminal}`; `404` if the job no longer exists. The page polls every 3 s, patches the panel, reloads on row-count growth, redirects to `/` on 404, stops at terminal.

### `GET /jobs/<id>/download.csv` (FR-006/006a)
Reconstructed `text/csv` attachment from persisted Utterances: `utteranceText,testId,<extra cols>`, **no password**. `<base>-reconstructed.csv`; non-terminal jobs also get `-partial` + an inline status/row-count marker. 404 if job unknown.

### `POST /jobs/<id>/cancel` (FR-018)
Iff status ∈ {queued, running} → `transition_to_cancelling`; `InvalidTransitionError` (raced to terminal) → 409 re-render with the current status. Else the control isn't shown. → redirect to detail.

### `POST /jobs/<id>/delete` (FR-019)
Iff status ∈ {draft, failed, cancelled} (re-checked in-txn) → `delete` (cascade) → `302 /` (dashboard). Else 409. Unknown id → 404.

---

## Cross-cutting
- **No secrets** anywhere in the rendered DOM (masked descriptors; never decrypt) — SC-003; satisfies the credential-masking cross-spec gate.
- **XSS-safe** (FR-007a): all evaluator-emitted data rendered via Jinja autoescape; never `|safe`.
- **No password** in the row projection or the reconstructed CSV (FR-008/006).
- **Snapshot is truth**: registries (013/014) are not consulted; archived registrations render the snapshot as-is.
