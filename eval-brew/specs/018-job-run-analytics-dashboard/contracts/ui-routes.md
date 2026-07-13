# UI Routes Contract: Job Run Analytics Dashboard (018)

**Generated**: 2026-07-08 | **Plan**: [plan.md](../plan.md)

---

## Route Summary

| Method | Path | Status | Auth | Description |
|---|---|---|---|---|
| GET | `/jobs/{job_id}/detail` | MODIFIED | required | Job detail page — now includes analytics context |
| GET | `/jobs/{job_id}/download-results.csv` | NEW | required | Long-format evaluated results CSV (terminal jobs only) |
| GET | `/jobs/{job_id}/download-results.json` | NEW | required | Nested evaluated results JSON (terminal jobs only) |
| GET | `/jobs/{job_id}/download.csv` | REMOVED | — | Retired reconstructed-input CSV (replaced by above) |
| GET | `/jobs/{job_id}/detail.json` | UNCHANGED | required | Live poller — status/counts JSON |
| POST | `/jobs/{job_id}/cancel` | UNCHANGED | required | Cancel a queued/running job |
| POST | `/jobs/{job_id}/delete` | UNCHANGED | required | Delete a terminal job |

---

## GET `/jobs/{job_id}/detail` — MODIFIED

### What changes

The route handler now calls the `RunAnalytics` engine after loading utterances and passes three additional keys to the template:

```python
analytics: RunAnalytics | None
analytics_skipped: bool          # True when total_utterance_count > 5000
analytics_empty: bool            # True when evaluated_count == 0 and not skipped
```

All existing template context keys (`meta`, `rows`, `declared_dimensions`, `selected`, etc.) are unchanged.

### Guard logic (order matters)

```python
if job.total_utterance_count > 5000:
    analytics = None
    analytics_skipped = True
    analytics_empty = False
elif evaluated_count == 0:
    analytics = None
    analytics_skipped = False
    analytics_empty = True
else:
    analytics = compute_analytics(entries, declared_dims)
    analytics_skipped = False
    analytics_empty = False
```

### Template rendering decision tree

```
analytics_skipped == True
  → Parameter Breakdown: show "report unavailable > 5,000 utterances" message
  → Job Overview analytics tiles: still render (overall_verdict_distribution + overall_mean_score derived from raw counts)

analytics_empty == True
  → Parameter Breakdown: show "no evaluated results" placeholder; sidebar anchor muted
  → Job Overview analytics tiles: render with zero-state values

analytics is RunAnalytics
  → Full dashboard renders
```

### Response

- **200 OK**: HTML page
- **404**: Job not found
- **403**: Requesting user does not own the job (if auth enabled)

---

## GET `/jobs/{job_id}/download-results.csv` — NEW

### Guard

Returns **404** if job is not in a terminal state (`completed`, `failed`, `cancelled`). The sidebar download button is hidden for non-terminal jobs; this guard is a server-side enforcement of FR-025.

### Response (success)

- **200 OK**
- `Content-Type: text/csv; charset=utf-8`
- `Content-Disposition: attachment; filename="{derived_filename}"`

### Filename derivation

```python
base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
filename = f"{base}-results.csv"
```

### Body

Long-format CSV. One row per utterance-parameter pair. Header row always present.

```
utteranceText,testId,chatbotResponse,overallVerdict,parameterName,score,verdict,reasoning
```

- `verdict` column: empty string when per-parameter verdict absent (v1 contract).
- Error utterances: included with `overallVerdict` set to error stage description; `parameterName`, `score`, `verdict`, `reasoning` all empty.
- Row ordering: by `utterance.row_index` ASC, then by declared-dimension order within each utterance.

### Error responses

- **404**: Job not found or not terminal
- **403**: Requesting user does not own the job

---

## GET `/jobs/{job_id}/download-results.json` — NEW

### Guard

Same as CSV: **404** if job is not terminal.

### Response (success)

- **200 OK**
- `Content-Type: application/json; charset=utf-8`
- `Content-Disposition: attachment; filename="{derived_filename}"`

### Filename derivation

```python
base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
filename = f"{base}-results.json"
```

### Body

JSON array. One element per utterance, ordered by `row_index` ASC.

```json
[
  {
    "utteranceText": "string",
    "testId": "string",
    "chatbotResponse": "string | null",
    "overallVerdict": "string | null",
    "errorStatus": "string | null",
    "errorStage": "string | null",
    "parameters": [
      {
        "parameter_name": "string",
        "score": 0.91,
        "reasoning": "string",
        "verdict": "string"
      }
    ]
  }
]
```

**Key rules**:
- `verdict` key inside parameter objects: **omitted** (not `null`) when the stored entry has no `verdict` field.
- `parameters` array: **empty array** for error utterances.
- `chatbotResponse`: `null` when `normalized_contract` is absent or `normalizedText` is missing.

### Error responses

- **404**: Job not found or not terminal
- **403**: Requesting user does not own the job

---

## GET `/jobs/{job_id}/download.csv` — REMOVED

This route (`view.reconstruct_csv()`) is removed entirely. The sidebar no longer renders the old "Export" card or any link to this path. Any external bookmarks or scripts using this URL will receive a **404** after this feature ships.

**Migration path**: Use `/jobs/{job_id}/download-results.csv` for evaluated results. Note the schema is different (long-format results vs. reconstructed input utterances).

---

## GET `/jobs/{job_id}/detail.json` — UNCHANGED

Live poller used by the existing table polling logic. Returns:

```json
{
  "status": "running",
  "badge_class": "badge-running",
  "status_label": "Running",
  "processed_count": 42,
  "failed_count": 1,
  "total_utterance_count": 100,
  "terminal": false,
  "row_count": 42
}
```

Analytics are **not** included in this endpoint. Analytics are static after page load (FR-028). The polling JS only uses this endpoint to detect new table rows and update counts — it does not refresh the analytics tiles.
