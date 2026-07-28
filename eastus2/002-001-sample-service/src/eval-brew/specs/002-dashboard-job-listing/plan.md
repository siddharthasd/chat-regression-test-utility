# Implementation Plan: Dashboard & Job Listing (Module 12)

**Branch**: `002-dashboard-job-listing` | **Date**: 2026-06-04 | **Spec**: `specs/002-dashboard-job-listing/spec.md`
**Base**: `foundation` (006-014 + 003, tip `24a85fa`, 323 passed / 7 xfailed / ruff clean)

## Summary

The harness's **root landing page**: a single scrollable table of every Job with color-coded status badges, the "Create New Job" entry into the wizard (003), per-row drill-in to the detail view (004, not yet built — handoff via a stable href), status/connector/created-by filters + name search + column sort (server-side), dashboard-cleanup delete (failed/cancelled only) + bulk "clear all failed and cancelled", and near-real-time updates of non-terminal rows via lightweight JSON polling. Read-only triage surface otherwise (no cancel/draft-delete here — those live in 004).

All row data comes straight from `Job` columns (the orchestrator already maintains `processed_count`/`failed_count`; `total_utterance_count` is set by 011) — no Utterance aggregation needed.

## Technical Context

**Language**: Python 3.11+ / Flask (matches 003/013/014). **Storage**: 009 via `JobRepository` + `get_session`. **Templating**: Jinja standalone `<!doctype html>` (no base layout — matches existing UIs). **Live updates**: vanilla-JS polling of a JSON endpoint (no build tooling, no new deps). **Testing**: pytest + Flask `test_client()` + per-test `engine.init_db(tmp)` isolation. **No new dependencies.**

**Reuse**:
- 009 `JobRepository`: **add** `list_all() -> list[Job]` (ordered `created_at` desc) — the only new 009 method; `delete(job_id)` (cascade), `delete_all_failed_and_cancelled() -> int`, `get(job_id)`.
- 009 `enums`: `JobStatus`, `TERMINAL_STATUSES` (drives badge set + stop-polling), `DELETABLE_STATUSES`.
- 003 wizard route `wizard.new_job` (the "Create New Job" target).
- 010 `tester_identity` context processor (already global) for the header.

## Source layout (new)

```
src/harness/ui/dashboard/__init__.py            # exports bp
src/harness/ui/dashboard/routes.py              # GET / ; GET /dashboard/jobs.json ; POST delete ; POST clear-terminal
src/harness/ui/dashboard/view.py                # row projection, filter/sort/search, hybrid timestamp + badge helpers
src/harness/ui/dashboard/templates/dashboard/index.html
tests/integration/test_dashboard_ui.py
```
**Edits**: `src/harness/ui/__init__.py` register `dashboard_bp`; `pyproject.toml` package-data `"harness.ui.dashboard"`; `src/harness/persistence/repositories/job.py` add `list_all()`.

## Routes (contract — see contracts/ui-routes.md)

| Method + path | Purpose |
|---|---|
| `GET /` | dashboard (root, FR-001); query params `status`/`connector`/`created_by` (multi), `q`, `sort`, `dir` drive server-side filter/sort/search |
| `GET /dashboard/jobs.json` | JSON of every job's live state (status, processed, total, failed, terminal) for the polling updater (FR-012/013) |
| `POST /dashboard/jobs/<id>/delete` | delete one job — **only if currently failed/cancelled** (re-checked at execute time); else 409 (FR-010b) |
| `POST /dashboard/clear-terminal` | `delete_all_failed_and_cancelled()` (FR-010c); redirect to `/` |

Row drill-in (FR-010): each row links to `/jobs/<id>/detail` (a literal href — 004 will own that route; the dashboard only does the handoff). Delete control uses a nested `<form>` so the row link is not triggered (FR-010/010b).

## view.py (pure, testable)

- `row_view(job) -> dict`: jobId, jobName, status, status_label (incl. "Completed with errors" when `status==completed and failed_count>0` — FR-005), badge_class, createdBy, createdAt/startedAt/completedAt as `(display, title)` hybrid (FR-003a), connectorName, `processed/total`, failedCount, harnessVersion, `deletable` (status in {failed, cancelled}), `terminal`.
- `apply_filters(rows, *, statuses, connectors, created_bys, q) -> list`: AND-combined (FR-006/007/008); empty filter list = no constraint.
- `sort_rows(rows, sort, direction)`: by underlying value; default `created_at` desc (FR-009/009a). Timestamps sort by the raw datetime, not the display string.
- `distinct_facets(jobs) -> {connectors, created_bys, statuses}`: option sets for the filter UI from persisted data (FR-006).
- `format_timestamp(dt, now) -> (display, title)`: relative < 24h ("just now"/"N minutes ago"/"N hours ago"), absolute `YYYY-MM-DD HH:MM` otherwise; the other form in `title` (FR-003a).

## Near-real-time updates (FR-012/013, SC-002/007)

`index.html` includes a small inline script: every 3 s `fetch('/dashboard/jobs.json')`, and for each job still rendered, update its status badge + `processed/total` + failed cells by `data-job-id`. When **every** rendered row is terminal, the script stops polling (SC-007). New/transitioning rows are picked up on the next natural page load (server-rendered); the poll covers the live-counter watch-window case which is the SC-002 requirement. The JSON endpoint is the tested surface; the script is a thin progressive enhancement.

## Delete gating (FR-010b/c, edge cases)

`POST /dashboard/jobs/<id>/delete`: re-read the job in the txn; if status not in {failed, cancelled} → 409 with an actionable message (handles the "status changed between confirm and execute" edge case); else `delete(job_id)` (009 cascade). `clear-terminal` uses 009's atomic `delete_all_failed_and_cancelled()`. The confirmation + exact count are rendered server-side (count from `list_all`).

## Constitution Check
Harness premises only (single-user, no auth — root page is unauthenticated; identity is the OS-derived header). No new deps. No secrets rendered (the dashboard shows no auth/credential fields at all). Gate: **PASS** (pre/post design).

## Phase 0 / 1 outputs
- `research.md` — R1–R8 (root route + list_all, row projection, hybrid timestamps, server-side filter/sort/search, live-update polling, delete gating + re-check, detail-view handoff href, empty-state split).
- `data-model.md` — Job List Row projection + facet derivation + filter/sort rules + JSON shape.
- `contracts/ui-routes.md` — route table + params + responses + gating.
- `quickstart.md` — seed jobs + walkthrough.
- CLAUDE.md SPECKIT marker → `specs/002-dashboard-job-listing/plan.md`.
