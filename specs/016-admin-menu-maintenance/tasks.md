# Tasks: Admin Menu & Job Maintenance

**Input**: Design documents from `specs/016-admin-menu-maintenance/`

**Prerequisites**: plan.md ✓, spec.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Repository methods needed by both US1 (stats panel) and US2 (action).
Must be complete before any user story work begins.

- [X] T001 Add `count_all()` and `count_clearable()` methods to `JobRepository` in `src/harness/persistence/repositories/job.py`

**Checkpoint**: Two new read-only query methods exist on `JobRepository`. All existing tests still pass.

---

## Phase 2: User Story 1 — Admin accesses Job Maintenance page (Priority: P1) 🎯 MVP

**Goal**: Admin can navigate to `/admin/maintenance` via an Admin dropdown in the nav
bar and see a stats panel showing total jobs, clearable jobs, and database file size.

**Independent Test**: Load `/admin/maintenance` as admin (auth disabled = synthetic
admin). Verify three stat values are rendered correctly. Confirm a non-admin (user
role) receives 403. Confirm the Admin dropdown is present in the nav HTML.

- [X] T002 [P] [US1] Add `GET /admin/maintenance` route returning stats to `src/harness/ui/admin/routes.py`
- [X] T003 [P] [US1] Create stats panel template `src/harness/ui/admin/templates/admin/maintenance.html` with total_jobs, clearable_jobs, db_size_mb display
- [X] T004 [US1] Add Admin dropdown (with Job Maintenance link) to nav bar in `src/harness/ui/templates/base.html`, visible to admin role only
- [X] T005 [US1] Write integration tests for stats page and role protection in `tests/integration/test_admin_maintenance.py`

**Checkpoint**: GET `/admin/maintenance` renders stats. Admin dropdown is visible for
admin, hidden for user. Non-admin GET returns 403.

---

## Phase 3: User Story 2 — Admin clears terminal jobs and vacuums the database (Priority: P2)

**Goal**: Admin submits the Clear & Vacuum form. All failed/cancelled/completed-with-errors
jobs are permanently deleted and the database is compacted. A flash message shows
rows deleted and DB size before/after.

**Independent Test**: Seed N terminal-status jobs. POST `/admin/maintenance`. Verify
N jobs deleted, clearable count is 0 on redirect, flash message contains both size
values.

- [X] T006 [US2] Add `_db_size_mb()` and `_vacuum_db()` helper functions to `src/harness/ui/admin/routes.py`
- [X] T007 [US2] Add `POST /admin/maintenance` route (delete_all_clearable → vacuum → flash) to `src/harness/ui/admin/routes.py`
- [X] T008 [US2] Update `src/harness/ui/admin/templates/admin/maintenance.html` — add Clear & Vacuum form with JavaScript confirm dialog showing clearable count
- [X] T009 [US2] Write integration tests for POST /admin/maintenance (zero jobs, N jobs, successful-only jobs untouched) in `tests/integration/test_admin_maintenance.py`

**Checkpoint**: POST `/admin/maintenance` deletes only terminal jobs, runs VACUUM,
redirects with flash showing deleted count and size change. Successful completed jobs
survive.

---

## Phase 4: User Story 3 — Users nav item moves under Admin dropdown (Priority: P3)

**Goal**: The standalone "Users" nav item is removed from the top level; Users is
accessible only via Admin dropdown alongside Job Maintenance.

**Independent Test**: Load any page as admin. Confirm no standalone "Users" `<a>`
tag exists outside the Admin dropdown. Confirm Admin dropdown contains both
"Job Maintenance" and "Users" links.

- [X] T010 [US3] Remove standalone Users nav item and add Users link inside Admin dropdown in `src/harness/ui/templates/base.html`
- [X] T011 [US3] Add nav structure assertions (no standalone Users, dropdown contains both links) to `tests/integration/test_admin_maintenance.py`

**Checkpoint**: All three user stories independently functional. Nav is clean.

---

## Phase 5: Polish

- [X] T012 Run full test suite and confirm all tests pass with `pytest tests/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: Depends on T001 (count methods)
- **US2 (Phase 3)**: Depends on US1 complete (POST route adds to routes.py already modified in T002; template already created in T003)
- **US3 (Phase 4)**: Depends on US1 complete (Admin dropdown in base.html already added in T004)
- **Polish (Phase 5)**: Depends on all user stories complete

### Within Each User Story

- T002 and T003 are [P] — different files, can be written simultaneously
- T004 depends on T002 (route name `admin_maintenance` must exist for `url_for`)
- T005 depends on T002, T003, T004 all complete (tests need working page)
- T006 must precede T007 (helpers used by POST route)
- T008 depends on T003 (extends the existing template)
- T009 depends on T007, T008 complete
- T010 depends on T004 (Admin dropdown must exist before Users is moved into it)
- T011 depends on T010

### Parallel Opportunities

```bash
# Phase 2 — T002 and T003 can be written in parallel (different files):
Task T002: GET /admin/maintenance route  →  src/harness/ui/admin/routes.py
Task T003: maintenance.html template     →  src/harness/ui/admin/templates/admin/maintenance.html
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Complete Phase 1 (T001)
2. Complete Phase 2 US1 (T002–T005)
3. **STOP and VALIDATE**: stats page works, Admin dropdown appears, role guard enforced

### Full Delivery

1. Phase 1 → Foundation ready
2. Phase 2 → Stats page + Admin dropdown (MVP)
3. Phase 3 → Clear & Vacuum action
4. Phase 4 → Nav reorganisation (Users under Admin)
5. Phase 5 → Full test suite green

---

## Notes

- `_vacuum_db()` must use `sqlite3.connect(str(resolve_db_path()))` directly — NOT
  `get_engine().connect()`. The engine's `enable_transactional_ddl` listener
  auto-emits `BEGIN` on every connection, and SQLite refuses VACUUM inside a
  transaction.
- `_db_size_mb()` should catch `OSError` and return `"unknown"` so a missing file
  path does not crash the stats page (edge case from spec).
- The confirm dialog message must interpolate the live `clearable_jobs` count:
  `"This will permanently delete {{ clearable_jobs }} clearable jobs and compact the database. Continue?"`
- Tests use `monkeypatch` + `TestClient(create_app())` pattern from `test_admin_users.py`.
  Auth is disabled in tests (synthetic admin) — no MSAL roundtrips needed.
