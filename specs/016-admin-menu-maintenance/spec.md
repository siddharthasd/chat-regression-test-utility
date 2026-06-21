# Feature Specification: Admin Menu & Job Maintenance

**Feature Branch**: `016-admin-menu-maintenance`

**Created**: 2026-06-21

**Status**: Draft

**Input**: User description: "Feature 017 — Admin Menu & Job Maintenance"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin accesses Job Maintenance page (Priority: P1)

An admin user opens the Admin dropdown from the navigation bar and navigates to the
Job Maintenance page. They see a stats panel showing total jobs, the number of
clearable jobs (failed, cancelled, and completed-with-errors), and the current
database file size. This gives them situational awareness before taking any action.

**Why this priority**: The stats panel is the foundation of the page — it must exist
before the action button is meaningful. It is also independently useful as a
read-only monitoring surface.

**Independent Test**: Can be fully tested by loading `/admin/maintenance` and
verifying the three stats values are present and accurate against the database
state. No action needs to be taken.

**Acceptance Scenarios**:

1. **Given** an admin is logged in, **When** they click the Admin dropdown in the
   nav bar, **Then** they see "Job Maintenance" and "Users" as menu items.
2. **Given** an admin clicks "Job Maintenance", **When** the page loads,
   **Then** they see total job count, clearable job count, and database file size
   in MB (2 decimal places).
3. **Given** a user (non-admin) is logged in, **When** they attempt to navigate to
   `/admin/maintenance`, **Then** they are denied access (redirected or shown a
   403 page).
4. **Given** auth is disabled (local dev mode), **When** any user loads the page,
   **Then** the Admin dropdown and Job Maintenance page are accessible (synthetic
   admin identity).

---

### User Story 2 - Admin clears terminal jobs and vacuums the database (Priority: P2)

An admin views the Job Maintenance page, sees N clearable jobs, and clicks
"Clear & Vacuum". A browser confirmation dialog shows the number of jobs about to
be deleted. After confirming, all failed, cancelled, and completed-with-errors jobs
are permanently deleted along with their associated records. The database is then
compacted. The page reloads with a success message showing how many jobs were
deleted and the database size before and after the operation.

**Why this priority**: This is the primary maintenance action. It depends on US1
(the stats panel) being in place first.

**Independent Test**: Can be fully tested by seeding the database with terminal-status
jobs, clicking "Clear & Vacuum", and verifying the jobs are gone and the flash
message reports correct counts and size change.

**Acceptance Scenarios**:

1. **Given** N clearable jobs exist, **When** the admin clicks "Clear & Vacuum",
   **Then** a confirmation dialog shows "This will permanently delete N clearable
   jobs and compact the database. Continue?"
2. **Given** the admin confirms, **When** the action completes, **Then** all
   failed, cancelled, and completed-with-errors jobs are removed from the database.
3. **Given** the action completes, **When** the page reloads, **Then** a flash
   message shows the number of jobs deleted and the database size before and after
   vacuum.
4. **Given** zero clearable jobs exist, **When** the admin submits the form,
   **Then** the action completes successfully with a message indicating zero jobs
   were deleted and the database was still vacuumed.
5. **Given** the admin clicks "Clear & Vacuum" and then cancels the confirmation
   dialog, **Then** no jobs are deleted and the page remains unchanged.
6. **Given** successful completed jobs (no errors) exist, **When** Clear & Vacuum
   runs, **Then** those jobs are NOT deleted — only terminal-state jobs are removed.

---

### User Story 3 - Users nav item moves under Admin dropdown (Priority: P3)

The existing "Users" link, previously a standalone item in the nav bar, is removed
from the top level and placed inside the Admin dropdown alongside "Job Maintenance".
Admins find all admin-facing pages in one consistent location.

**Why this priority**: This is a nav reorganisation that depends on the Admin
dropdown (US1) existing first. It delivers no new capability but improves nav
consistency.

**Independent Test**: Can be tested by verifying no standalone "Users" nav item
exists and that the Admin dropdown contains both "Job Maintenance" and "Users" links.

**Acceptance Scenarios**:

1. **Given** an admin is logged in, **When** they look at the nav bar, **Then**
   there is no standalone "Users" item — only the "Admin" dropdown.
2. **Given** an admin opens the Admin dropdown, **When** they click "Users",
   **Then** they are taken to `/admin/users`.
3. **Given** a regular user is logged in, **When** they look at the nav bar,
   **Then** the Admin dropdown is not visible.

---

### Edge Cases

- What happens when the database file cannot be found for size calculation? Display
  "unknown" rather than crashing the page.
- What happens if a vacuum fails mid-operation? The delete phase has already
  committed; the flash message should indicate that deletes succeeded but vacuum
  did not complete, without rolling back the deletes.
- What if another user submits a job during the vacuum operation? The vacuum holds
  an exclusive lock briefly; concurrent writes queue and succeed once vacuum
  completes (SQLite behaviour — no special handling needed).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The navigation bar MUST include an "Admin" dropdown menu visible only
  to users with the admin role (or always when auth is disabled).
- **FR-002**: The Admin dropdown MUST contain two items: "Job Maintenance"
  (links to `/admin/maintenance`) and "Users" (links to `/admin/users`).
- **FR-003**: The standalone "Users" nav item MUST be removed from the top-level
  navigation; it MUST only appear inside the Admin dropdown.
- **FR-004**: The Job Maintenance page MUST display three read-only stats: total
  job count (all statuses), clearable job count (failed + cancelled +
  completed-with-errors), and database file size in MB (2 decimal places).
- **FR-005**: The Job Maintenance page MUST be accessible only to admin users;
  non-admin access MUST be denied.
- **FR-006**: The page MUST provide a single "Clear & Vacuum" action button.
- **FR-007**: The "Clear & Vacuum" button MUST show a browser confirmation dialog
  before submitting, displaying the number of clearable jobs.
- **FR-008**: On confirmation, the action MUST permanently delete all failed,
  cancelled, and completed-with-errors jobs along with all their associated
  utterance and evaluation result records.
- **FR-009**: Successfully completed jobs (zero errors) MUST NOT be deleted by
  this action.
- **FR-010**: After the delete commits, the system MUST run a database vacuum
  operation to compact the database file.
- **FR-011**: After the action completes, the page MUST display a flash message
  reporting: number of jobs deleted, database size before vacuum, and database
  size after vacuum.

### Key Entities

- **Job**: Existing entity. Terminal statuses eligible for clearing: FAILED,
  CANCELLED, COMPLETED-with-errors (completed status + failed_count > 0).
- **Database file**: The SQLite file on disk. Its path is read from configuration.
  Size is measured in bytes and displayed as MB.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An admin can navigate from the dashboard to the Job Maintenance page
  in two clicks (Admin dropdown → Job Maintenance).
- **SC-002**: The stats panel accurately reflects the current database state on
  every page load with no manual refresh required.
- **SC-003**: The Clear & Vacuum action completes within 10 seconds for a database
  containing up to 10,000 jobs and their associated records.
- **SC-004**: After a successful Clear & Vacuum, the clearable job count on the
  refreshed page is zero.
- **SC-005**: The flash message after Clear & Vacuum shows a non-zero size
  reduction when clearable jobs were present before the action.
- **SC-006**: No successful completed jobs are missing from the database after a
  Clear & Vacuum operation.

## Assumptions

- The admin blueprint and `require_auth` / `require_role` decorators from Feature
  015 are already in place; this feature adds routes to the existing blueprint
  without changing the auth infrastructure.
- The existing `delete_all_clearable()` method on `JobRepository` covers the
  correct scope (FAILED, CANCELLED, COMPLETED-with-errors) and will be reused
  without modification.
- The database file path is accessible to the server process at runtime (needed
  for file size calculation).
- The vacuum operation is expected to take up to a few seconds on the target
  deployment; a loading indicator is not required for v1 but the admin should be
  informed via the confirmation dialog that the operation may take a moment.
- Auth-disabled mode (local dev) treats all users as synthetic admins; the Admin
  dropdown and Job Maintenance page are therefore always accessible in that mode.
- The existing "Clear errors" button on the dashboard is out of scope — it remains
  unchanged and operates on the current user's own visible terminal jobs only.
