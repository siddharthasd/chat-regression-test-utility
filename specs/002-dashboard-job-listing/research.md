# Phase 0 Research: Dashboard & Job Listing (Module 12)

**Date**: 2026-06-04 | **Plan**: `specs/002-dashboard-job-listing/plan.md`

Built on `foundation`. Server-rendered Flask + thin polling JS, no new deps.

---

## R1: Root route + list-all (FR-001/002)
**Decision**: register the dashboard at `GET /` (the harness root). Add `JobRepository.list_all() -> list[Job]` ordered by `created_at` desc (default sort, FR-009a). Render every job in one scrollable table (no pagination/virtualization — FR-002).
**Rationale**: the spec mandates the dashboard be the root landing page; a single read method on the owning repo (009) is the clean source. 1,000-job target renders fine as one table.

## R2: Row projection from Job columns (FR-003)
**Decision**: `row_view(job)` reads `Job` columns directly — `processed_count`/`failed_count`/`total_utterance_count` are already maintained (orchestrator + 011), so **no Utterance aggregation**. "Completed with errors" is derived (`status==completed and failed_count>0`), not stored (FR-005).
**Rationale**: 009 FR-001 makes the counters first-class Job columns; the dashboard is a pure projection.

## R3: Hybrid timestamps (FR-003a)
**Decision**: `format_timestamp(dt, now) -> (display, title)`: `< 24h` → relative ("just now", "N minutes ago", "N hours ago"); else absolute `YYYY-MM-DD HH:MM`. The alternate form goes in the cell's `title` (hover). Sorting uses the raw datetime, never the display string.
**Rationale**: matches the clarified hybrid format; keeping sort keyed on the datetime avoids lexicographic-on-display bugs.

## R4: Server-side filter / sort / search (FR-006/007/008/009)
**Decision**: filters + search + sort are driven by query params on `GET /` and applied in `view.py` (`apply_filters` AND-combines status/connector/created_by multi-selects + case-insensitive name substring; `sort_rows` by underlying value, default created_at desc). Facet option sets (`distinct_facets`) are the distinct values present in persisted Jobs (FR-006 — no separate registry).
**Rationale**: server-side is fully functional without JS and directly testable via the Flask test client; the 200 ms SC-003 budget is trivially met for ≤1,000 rows. Live re-evaluation across updates (FR-008a) is approximated by the next render; the watch-window requirement (SC-002) is covered by R5.
**Alternatives**: full client-side filtering (needs a JS framework / build step — out of scope for this server-rendered harness) — rejected.

## R5: Near-real-time updates (FR-012/013, SC-002/007)
**Decision**: `GET /dashboard/jobs.json` returns every job's live state (`status`, `processed`, `total`, `failed`, `terminal`). `index.html` polls it every 3 s and patches each rendered row's badge + counters by `data-job-id`; when all rendered rows are terminal it stops polling (SC-007). The JSON endpoint is the tested surface; the script is a progressive enhancement.
**Rationale**: polling needs no new deps and no persistent connection; 3 s comfortably meets the ≤5 s SC-002 bound. SSE/WebSocket are heavier and unnecessary for a single-user localhost tool.

## R6: Delete gating + execute-time re-check (FR-010b/c, edge cases)
**Decision**: `POST /dashboard/jobs/<id>/delete` re-reads the job inside the txn and deletes **only** if status is `failed`/`cancelled`, else 409 with an actionable message (covers "status changed between confirm and execute"). The delete control renders **only** on failed/cancelled rows. `clear-terminal` uses 009's atomic `delete_all_failed_and_cancelled()`; the confirm prompt shows the exact count (from `list_all`).
**Rationale**: reuses 009's cascade + atomic bulk delete; the route-level status gate enforces the dashboard's narrower rule (009's `delete` also allows `draft`, which the dashboard must NOT expose).

## R7: Detail-view handoff (FR-010, 004 not built)
**Decision**: each row body links to the literal path `/jobs/<id>/detail` (a plain `href`, **not** `url_for` — 004 will own that endpoint). The in-row delete control is a nested `<form>`/button so activating it doesn't trigger the row link (FR-010/010b).
**Rationale**: `url_for` on a not-yet-registered endpoint raises `BuildError` at render; a literal href is the honest handoff stub that 004 will satisfy. Tests assert the href is present, not that it resolves.

## R8: Two distinct empty states (FR-014/015)
**Decision**: "no jobs in the database" (from `list_all() == []`) renders the Create-New-Job CTA; "no rows match the active filters/search" (filtered set empty but jobs exist) renders a separate message + a one-click clear-filters link to `GET /`.
**Rationale**: the spec explicitly requires the two states be distinguishable; deriving them from `len(all)` vs `len(filtered)` is unambiguous.

---

*All decisions resolved. Implementation can proceed.*
