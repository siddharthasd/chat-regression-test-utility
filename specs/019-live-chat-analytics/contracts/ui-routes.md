# UI Routes Contract: Live Chat Session Analytics (019)

**Generated**: 2026-07-08 | **Plan**: [plan.md](../plan.md)

---

## Route Summary

| Method | Path | Status | Auth | Description |
|---|---|---|---|---|
| GET | `/chat/sessions/{session_id}/analytics` | NEW | required (owner only) | Session analytics page |
| GET | `/chat/sessions/{session_id}/download-results.csv` | NEW | required (owner only) | Long-format evaluated results CSV |
| GET | `/chat/sessions/{session_id}/download-results.json` | NEW | required (owner only) | Nested evaluated results JSON |
| GET | `/chat/sessions/{session_id}` | MODIFIED | required | Session interface — "Analytics" link added |

All other `/chat/sessions/{session_id}/*` routes (turns, export, delete, etc.) are UNCHANGED.

---

## GET `/chat/sessions/{session_id}/analytics` — NEW

### Handler

```python
@router.get("/chat/sessions/{session_id}/analytics")
async def chat_session_analytics(
    request: Request,
    session_id: str,
    user=Depends(require_auth),
):
```

### Access control

The handler calls `_require_session(repo, session_id, user)` (existing helper) which resolves the session and raises **404** if the session does not exist or the requesting user is not the owner. This is consistent with the owner-scope access used by every other session route. Admins cannot view another user's analytics page (FR-002).

### Computation flow

```python
session = _require_session(repo, session_id, user)
turns = repo.get_turns_with_results(session_id)

total_turns = session.total_turn_count
completed_turns = sum(1 for t in turns if t.status == "completed")
failed_turns = sum(1 for t in turns if t.status == "failed")

if total_turns > 5000:
    analytics = None
    analytics_skipped = True
    analytics_empty = False
else:
    entries = score_entries_from_turns(turns)
    evaluated_count = len([e for e in entries if not e.error])
    if evaluated_count == 0:
        analytics = None
        analytics_skipped = False
        analytics_empty = True
    else:
        declared_dims = session.evaluator_declared_scoring_dimensions or []
        analytics = compute_analytics(entries, declared_dims)
        analytics_skipped = False
        analytics_empty = False

turn_rows = turn_explorer_view(turns)
```

### Template rendering decision tree

```
analytics_skipped == True
  → Parameter Breakdown: "Analytics unavailable for sessions > 5,000 turns. Use Download CSV or Download JSON."
  → Session Overview: renders normally (counts available from ORM)

analytics_empty == True
  → Parameter Breakdown: informational placeholder; sidebar "Parameter Breakdown" anchor visually muted
  → Session Overview: renders with zero-state values

analytics is RunAnalytics
  → Full dashboard renders (all sections, all tiles)
```

### Response

- **200 OK**: HTML page (`analytics.html`)
- **404**: Session not found or requesting user is not the owner

---

## GET `/chat/sessions/{session_id}/download-results.csv` — NEW

### Handler

```python
@router.get("/chat/sessions/{session_id}/download-results.csv")
async def download_session_results_csv(
    request: Request,
    session_id: str,
    user=Depends(require_auth),
):
```

### Access control

Same `_require_session()` call as the analytics page handler. **404** if not found or not owner.

### Guard

**No terminal-state restriction.** Downloads are always available (FR-021). In-progress turns are excluded at the `results_csv_builder` level.

### Response (success)

- **200 OK**
- `Content-Type: text/csv; charset=utf-8`
- `Content-Disposition: attachment; filename="{derived_filename}"`

### Filename derivation

```python
from harness.ui.chat_session.view import _sanitise_session_name

sanitised = _sanitise_session_name(session.session_name or "")
if not sanitised:
    sanitised = f"session-{session_id[:8]}"
filename = f"{sanitised}-results.csv"
```

### Body

Long-format CSV. One row per turn-parameter pair. Header row always present.

```
turnIndex,userMessage,assembledResponse,overallVerdict,parameterName,score,verdict,reasoning
```

- `verdict` column: empty string when per-parameter verdict absent (v1 contract).
- Failed turns: one row with `overallVerdict` = error description; `parameterName`, `score`, `verdict`, `reasoning` all empty.
- In-progress turns: excluded.
- Row ordering: by `turn.turn_index` ASC, then by declared-dimension order within each turn.

### Edge case — no completed turns

The file is produced with only the header row. HTTP status is **200** (not an error). The file body is a single header line.

### Error responses

- **404**: Session not found or requesting user is not the owner

---

## GET `/chat/sessions/{session_id}/download-results.json` — NEW

### Handler

```python
@router.get("/chat/sessions/{session_id}/download-results.json")
async def download_session_results_json(
    request: Request,
    session_id: str,
    user=Depends(require_auth),
):
```

### Access control

Same `_require_session()` call. **404** if not found or not owner.

### Guard

No terminal-state restriction. In-progress turns excluded at builder level.

### Response (success)

- **200 OK**
- `Content-Type: application/json; charset=utf-8`
- `Content-Disposition: attachment; filename="{derived_filename}"`

### Filename derivation

Same sanitisation logic as CSV; `.json` extension.

### Body

JSON array. One element per turn ordered by `turn_index` ASC.

```json
[
  {
    "turnIndex": 1,
    "userMessage": "string",
    "assembledResponse": "string | null",
    "overallVerdict": "string | null",
    "errorStatus": "string | null",
    "errorStage": "string | null",
    "parameters": [
      {
        "parameter_name": "string",
        "score": 0.91,
        "reasoning": "string"
      }
    ]
  }
]
```

**Key rules**:
- `verdict` key inside parameter objects: **omitted** (not `null`) when the stored entry has no `verdict` field (v1 contract).
- `parameters` array: empty `[]` for failed turns.
- `assembledResponse`: `null` when `ChatTurnResult` is absent or has no assembled text.

### Edge case — no completed turns

Returns an empty JSON array `[]`. HTTP status **200**.

### Error responses

- **404**: Session not found or requesting user is not the owner

---

## GET `/chat/sessions/{session_id}` — MODIFIED

### What changes

The session interface template (`interface.html`) gains a single "Analytics" affordance: a link or button in the session header or action bar that navigates to `/chat/sessions/{session_id}/analytics`.

No route handler logic changes. The route signature and response shape are unchanged.

### Link specification

```html
<a href="/chat/sessions/{{ session.chat_session_id }}/analytics"
   class="btn btn-sm btn-outline-secondary">
  Analytics
</a>
```

Position: adjacent to existing session header actions (rename, delete, export). Exact position within the header is implementation-discretion.

---

## Tooltip Copy Constants

The route handler for `chat_session_analytics` passes `tooltip_copy` to the template as a Python dict. The values are the canonical metric explanations from `specs/019-live-chat-analytics/spec.md` section "Metric Explanations — Canonical Copy." The dict is assembled inline in `routes.py` (or as a module-level constant in `view.py`).

Keys: `"Mean"`, `"Median"`, `"Min"`, `"Max"`, `"Range"`, `"σ"`, `"Overall Mean Score"`, `"Overall Verdict Distribution"`.
