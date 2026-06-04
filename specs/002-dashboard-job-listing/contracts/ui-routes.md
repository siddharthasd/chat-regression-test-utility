# Contract: Dashboard UI Routes (Module 12)

**Date**: 2026-06-04
Server-rendered Flask blueprint `dashboard`, mounted at the harness root. Read-only triage + cleanup. Consumes 009 (`JobRepository`), links to 003 (wizard) and 004 (detail, not yet built).

---

## Routes

### `GET /` — the dashboard (FR-001/002)
Query params (all optional): `status` (repeatable), `connector` (repeatable), `created_by` (repeatable), `q` (name substring), `sort` (column), `dir` (`asc`|`desc`). Renders the full table after `apply_filters` + `sort_rows`. Shows:
- "Create New Job" → `url_for('wizard.new_job')` (FR-011, present in both empty + populated states).
- "Clear all failed and cancelled" with the exact count; disabled when count == 0 (FR-010c).
- Filter controls populated from `distinct_facets` (FR-006), a search box (FR-007), sortable column headers (FR-009).
- Empty states: no-jobs CTA vs no-matches + clear-filters (FR-014/015).
Each row: `data-job-id`, color-coded status badge (FR-004/005), hybrid timestamps (FR-003a), a body link to `/jobs/<id>/detail` (FR-010 handoff to 004), and — only on failed/cancelled rows — a delete button in a nested form (FR-010b).

### `GET /dashboard/jobs.json` — live state (FR-012/013)
`200 {"jobs": [{job_id, status, status_label, processed, total, failed, terminal}, ...]}` for every job. The page's poller patches non-terminal rows every 3 s and stops once all rendered rows are terminal (SC-002/007).

### `POST /dashboard/jobs/<id>/delete` (FR-010b)
Re-reads the job in-txn; if status ∈ {failed, cancelled} → `delete(job_id)` (cascade) → `302 /` ; else → `409` re-render with "job is <status> and cannot be deleted from the dashboard". Unknown id → 404.

### `POST /dashboard/clear-terminal` (FR-010c)
`delete_all_failed_and_cancelled()` (atomic) → `302 /`. No-op safe when count is 0.

---

## Cross-cutting
- **No auth** (root is unauthenticated); OS identity via the shared `tester_identity` context processor.
- **No secrets**: the dashboard renders no auth/credential fields at all.
- **Row vs control**: the delete control is a nested `<form>` so it never triggers the row's drill-in link (FR-010).
- **004 handoff**: row links use the literal `/jobs/<id>/detail` path (004 will register it); the dashboard only performs the navigation handoff.
