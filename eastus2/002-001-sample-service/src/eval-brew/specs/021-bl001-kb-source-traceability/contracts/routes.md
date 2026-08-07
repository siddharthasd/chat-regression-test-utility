# Route Contracts: BL-001 KB Source Traceability

---

## Existing routes — behaviour changes only

### `GET /jobs/{job_id}/download-results.csv`

No path change. Behaviour changes:
- Response now includes two additional columns at the end of every row: `sourceCount` (int), `retrievedSources` (JSON string).
- Download button label in the UI changes to **"PBI Compatible CSV Download"**.
- All other behaviour unchanged (terminal-only guard, 404 on missing/non-terminal job, `Content-Disposition: attachment`).

### `GET /jobs/{job_id}/download-results.json`

No path change. Behaviour changes:
- Each utterance object in the response array now includes a `sources` key (array of source objects, `[]` when none).
- Download button label in the UI changes to **"JSON Download"**.
- All other behaviour unchanged.

---

## New route

### `GET /jobs/{job_id}/download-results.xlsx`

**Auth**: `require_auth` (same dependency as CSV/JSON routes).  
**Guard**: terminal jobs only (`status in {completed, failed, cancelled}`). Returns `404` for non-existent job or non-terminal status.  
**Response**:

```
HTTP 200
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="{base}-results.xlsx"
Body: openpyxl Workbook serialised to BytesIO — no disk writes
```

**Error responses**:

| Condition | Status |
|---|---|
| Job not found | 404 |
| Job is not terminal | 404 |

**Implementation** (in `src/harness/ui/detail/routes.py`):

```python
@router.get("/jobs/{job_id}/download-results.xlsx")
def download_results_xlsx(
    request: Request,
    job_id: str,
    user: dict = Depends(require_auth),
):
    """Multi-sheet XLSX results export; terminal jobs only."""
    with get_session() as session:
        job = JobRepository(session).get(job_id)
        if job is None or job.status not in _TERMINAL:
            raise HTTPException(status_code=404)
        utterances = UtteranceRepository(session).get_by_job_ordered(job_id)
        filename, body = results_xlsx_builder(job, utterances)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

---

## Template changes (`detail/index.html`)

### Download buttons — terminal state

**Before:**
```html
<a href="/jobs/{{ meta.job_id }}/download-results.csv"
   class="btn btn-sm btn-outline-primary">Download CSV</a>
<a href="/jobs/{{ meta.job_id }}/download-results.json"
   class="btn btn-sm btn-outline-primary">Download JSON</a>
```

**After:**
```html
<a href="/jobs/{{ meta.job_id }}/download-results.csv"
   class="btn btn-sm btn-outline-primary">PBI Compatible CSV Download</a>
<a href="/jobs/{{ meta.job_id }}/download-results.xlsx"
   class="btn btn-sm btn-outline-primary">PBI Compatible XLSX Download</a>
<a href="/jobs/{{ meta.job_id }}/download-results.json"
   class="btn btn-sm btn-outline-primary">JSON Download</a>
```

### Download buttons — non-terminal (disabled) state

**Before:**
```html
<button ... disabled title="Available after job completes">Download CSV</button>
<button ... disabled title="Available after job completes">Download JSON</button>
```

**After:**
```html
<button ... disabled title="Available after job completes">PBI Compatible CSV Download</button>
<button ... disabled title="Available after job completes">PBI Compatible XLSX Download</button>
<button ... disabled title="Available after job completes">JSON Download</button>
```

### Retrieved Context section — expand/trace panel

Insert **before** the existing `{% for label, artifact in [...] %}` artifact loop (line ~577), inside the `<details>` expand block:

```html
<!-- Retrieved Context -->
<div class="mb-3">
  <strong class="small">Retrieved Context</strong>
  <span class="badge bg-secondary ms-1" style="font-size:.7rem">
    {{ r.source_count }} source{% if r.source_count != 1 %}s{% endif %} retrieved
  </span>
  {% if r.sources %}
  <details class="mt-1">
    <summary class="small" style="cursor:pointer">Show sources</summary>
    <table class="table table-sm table-bordered mt-2 small">
      <thead class="table-light">
        <tr>
          <th>Title</th>
          <th>Scope</th>
          <th>Document ID</th>
          <th>Chunk</th>
        </tr>
      </thead>
      <tbody>
        {% for src in r.sources %}
        <tr>
          <td><a href="{{ src.url }}" target="_blank" rel="noopener">{{ src.title }}</a></td>
          <td><span class="badge bg-light text-dark border">{{ src.scope }}</span></td>
          <td class="text-muted">{{ src.documentId }}</td>
          <td>
            {% if src.chunk | length > 200 %}
            <details>
              <summary style="cursor:pointer">{{ src.chunk_short }}</summary>
              <div class="mt-1">{{ src.chunk }}</div>
            </details>
            {% else %}
            {{ src.chunk }}
            {% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </details>
  {% else %}
  <p class="text-muted small mt-1 mb-0">No context retrieved</p>
  {% endif %}
</div>
```

---

## Angular migration plan forward-compatibility

When Phase 1 of `docs/plans/plan-angular21-azure-functions-migration.md` is implemented, make these two one-line changes:

1. **REST API spec** (`GET /api/v1/jobs/{id}/export`, plan line 146): change `format=csv|json` → `format=csv|json|xlsx`
2. **`JobService.export()` TypeScript type** (plan line 604): change `format: 'csv' | 'json'` → `format: 'csv' | 'json' | 'xlsx'`

The Angular `ExportService.downloadBlob()` and `ApiService.downloadBlob()` patterns handle binary blob responses already — no Angular code changes beyond those two additions.
