# Contract: Connector Registry UI Routes

**Module**: `harness.ui.connector_registry` (Flask Blueprint, registered in `create_app()`).
**Surface**: server-rendered HTML; single-user localhost (no auth, no CSRF in v1).

---

## Routes

| Method + Path | Purpose | FR |
|---|---|---|
| `GET /connectors` | List view; query params `filter=active|archived|all` (default active), `q=<substr>` | FR-007/008/009/010 |
| `GET /connectors/new` | Empty create form | FR-001/002 |
| `POST /connectors` | Create; on validation error re-render form with errors; else redirect to list | FR-003/004 |
| `GET /connectors/<id>/edit` | Edit form pre-populated; secrets masked; `connectorId` read-only | FR-011/013 |
| `POST /connectors/<id>` | Update (form field `replace_credential` toggles re-encrypt) | FR-012 |
| `POST /connectors/<id>/archive` | Archive → redirect to list | FR-014 |
| `POST /connectors/<id>/restore` | Restore → redirect to list | FR-016 |
| `POST /connectors/<id>/delete` | Hard-delete; blocked (re-render with message) if referenced by Jobs | FR-018/019 |
| `POST /connectors/test-connection` | Run test connection from current form values; return `_test_result.html` fragment | FR-021–025 |

Bulk archive/restore/delete MAY post a list of ids to the same handlers (FR-014; spec "Assumptions").

## Form fields (create/edit)

`display_name` (text, required), `description` (text), `endpoint_url` (url, required), `auth_mode` (select: none/bearer/api-key-header/basic), conditional credential inputs per mode (FR-005; secrets `type=password`, masked), `timeout_seconds` (number, default 30), `expects_per_row_password` (checkbox). Edit adds a read-only `connectorId` and a "Replace credential" toggle.

## Masking & safety rules

- Credential values are **never** rendered (list, edit form, test-result) — only the mode label and (api-key-header) the header name (FR-010, SC-002). Edit shows a masked placeholder, never the stored value (FR-011).
- "Test connection" returns an informational fragment only; it never enables/disables Save and writes nothing (FR-024, SC-008).
- Validation errors re-render the form with the offending field flagged and an inline message (FR-004); the destructive delete uses a confirm step and shows the referencing-job count when blocked (FR-019).
- Empty state (zero registrations) shows a "Register your first connector" call-to-action.
