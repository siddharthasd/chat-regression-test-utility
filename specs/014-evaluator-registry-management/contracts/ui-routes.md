# Contract: Evaluator Registry UI Routes

**Module**: `harness.ui.evaluator_registry` (Flask Blueprint, registered in `create_app()`).
**Surface**: server-rendered HTML; single-user localhost (no auth/CSRF in v1). Mirrors `013`.

---

## Routes

| Method + Path | Purpose | FR |
|---|---|---|
| `GET /evaluators` | List view; `filter=active|archived|all` (default active), `q=<substr>` | FR-012/013/014/015 |
| `GET /evaluators/new` | Empty create form | FR-001/002 |
| `POST /evaluators` | Create; re-render with errors or redirect to list | FR-003/004 |
| `GET /evaluators/<id>/edit` | Edit form pre-populated; secrets masked; id read-only; dimensions textarea | FR-016/018 |
| `POST /evaluators/<id>` | Update (`replace_credential` toggle) | FR-017 |
| `POST /evaluators/<id>/archive` | Archive → list | FR-019 |
| `POST /evaluators/<id>/restore` | Restore → list | FR-021 |
| `POST /evaluators/<id>/delete` | Hard-delete; blocked when referenced | FR-023/024 |
| `POST /evaluators/test-connection` | Run test connection from form values; return `_test_result.html` | FR-026–030 |

## Form fields (create/edit)

`display_name` (required), `description` (**required**), `endpoint_url` (required url), `auth_mode` (select), conditional credential inputs per mode (secrets `type=password`, masked), `timeout_seconds` (number, default 60), `dimensions` (textarea, one dimension per line — order preserved). Edit adds a read-only `evaluation_agent_id` and a "Replace credential" toggle.

## Masking & safety rules

- Credentials never rendered (list, edit, test-result) — only mode label + (api-key-header) header name (FR-015, SC-002); edit shows a masked placeholder (FR-016).
- Dimensions preview on the list: first 3 in declared order + `+ N more` (FR-015).
- "Test connection" returns an informational fragment (incl. a soft warning for divergent dimensions); never blocks Save, writes nothing (FR-030, SC-009).
- Validation errors re-render the form with the offending field flagged (FR-004); a duplicate-dimension condition shows a non-blocking warning but still saves (FR-009).
- Empty state (zero registrations): "Register your first evaluator" call-to-action.
