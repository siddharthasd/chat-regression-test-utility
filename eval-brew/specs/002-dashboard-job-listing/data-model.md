# Phase 1 Data Model: Dashboard & Job Listing (Module 12)

**Date**: 2026-06-04 | **Plan**: `specs/002-dashboard-job-listing/plan.md`

The dashboard owns **no entity** — it projects 009 `Job` rows. One new read method on 009 (`list_all`).

---

## 1. Job List Row projection (`view.row_view(job)`) — FR-003

| Field | Source | Notes |
|---|---|---|
| `job_id` | `Job.job_id` | row key + drill-in href |
| `job_name` | `Job.job_name` | truncated in UI w/ title |
| `status` | `Job.status` | raw enum value |
| `status_label` | derived | "Completed with errors" when `status==completed and failed_count>0` (FR-005) |
| `badge_class` | derived | per-status CSS class for the color-coded badge (FR-004) |
| `created_by` | `Job.created_by` | OS-derived (FR-026) |
| `created_at`/`started_at`/`completed_at` | `Job.*` | each → `(display, title)` hybrid (FR-003a); nullable → "—" |
| `connector_name` | `Job.connector_name` | verbatim snapshot of registration displayName |
| `processed` / `total` | `Job.processed_count` / `Job.total_utterance_count` | rendered `processed/total` |
| `failed_count` | `Job.failed_count` | |
| `harness_version` | `Job.harness_version` | |
| `deletable` | derived | `status in {failed, cancelled}` (FR-010b) |
| `terminal` | derived | `status in TERMINAL_STATUSES` (stop-polling) |

## 2. Facets (`view.distinct_facets(jobs)`) — FR-006
- `statuses`: the canonical enum order, intersected-or-all.
- `connectors`: distinct non-null `Job.connector_name` across all jobs.
- `created_bys`: distinct `Job.created_by` across all jobs.
No registry consulted — purely values present in persisted Jobs.

## 3. Filter / sort / search (server-side) — FR-006/007/008/009/009a
- `apply_filters(rows, statuses, connectors, created_bys, q)`: keep a row iff (no status filter or `status in statuses`) AND (no connector filter or `connector_name in connectors`) AND (no created_by filter or `created_by in created_bys`) AND (no `q` or `q.lower() in job_name.lower()`). AND-combined (FR-008).
- `sort_rows(rows, sort, direction)`: key by the underlying column value (datetimes by raw `datetime`, ints by int, strings case-insensitively); default `sort=created_at`, `dir=desc` (FR-009a). Nulls sort last.

## 4. Live-update JSON (`GET /dashboard/jobs.json`) — FR-012/013
```json
{"jobs": [
  {"job_id": "...", "status": "running", "status_label": "Running",
   "processed": 12, "total": 50, "failed": 1, "terminal": false}
]}
```
The poller patches rendered rows by `data-job-id`; stops when all rendered rows are `terminal`.

## 5. Empty states — FR-014/015
| Condition | State |
|---|---|
| `list_all() == []` | "No jobs yet" + Create-New-Job CTA |
| jobs exist but filtered set empty | "No matches" + clear-filters link |

## 6. Mutations
| Route | Rule | Repo |
|---|---|---|
| `POST /dashboard/jobs/<id>/delete` | only if status ∈ {failed, cancelled} (re-checked in txn) else 409 | `JobRepository.delete` (cascade) |
| `POST /dashboard/clear-terminal` | delete all failed+cancelled atomically | `JobRepository.delete_all_failed_and_cancelled` |

## 7. New 009 method
`JobRepository.list_all() -> list[Job]` — `select(Job).order_by(Job.created_at.desc())`.
