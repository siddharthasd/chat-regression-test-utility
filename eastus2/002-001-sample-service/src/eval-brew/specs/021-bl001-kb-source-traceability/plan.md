# Implementation Plan: BL-001 — KB Source Traceability

**Branch**: `021-bl001-kb-source-traceability` | **Date**: 2026-08-07  
**Backlog item**: `docs/backlog/BL-001-context-display-kb-article-traceability.md`  
**Spec dir**: `specs/021-bl001-kb-source-traceability/`

---

## Summary

Surfaces `chatbotResponse.metadata.sources` — already persisted in
`evaluation_result.normalized_contract` — in three places: the results expand/trace
panel in the UI, the CSV download (renamed to PBI Compatible CSV Download), and a new
PBI Compatible XLSX Download (three-sheet workbook). The JSON download also gains a
`sources` array on each utterance object.

**No database migration. No contract extension. No new tables.** All changes are
read-and-render against data already in the database.

---

## Technical Context

**Language/Version**: Python 3.11+  
**Framework**: FastAPI — existing `src/harness/ui/detail/` router  
**Template engine**: Jinja2 — `src/harness/ui/detail/templates/detail/index.html`  
**Storage**: Read-only against `evaluation_result.normalized_contract` (JSON column, SQLAlchemy 2.0)  
**New dependency**: `openpyxl>=3.1,<4` — confirmed absent; must be added to `pyproject.toml`  
**Streaming**: `io.BytesIO` — in-memory only; no disk writes; compatible with Azure Function App Premium EP1  
**Testing**: pytest — existing `TestClient` pattern; existing `conftest.py` savepoint isolation  

**Files changed** (no new modules, no new packages beyond `openpyxl`):

| File | Change type |
|---|---|
| `src/harness/ui/detail/view.py` | Edit — 3 functions modified, 1 new function |
| `src/harness/ui/detail/routes.py` | Edit — 1 new route added |
| `src/harness/ui/detail/templates/detail/index.html` | Edit — buttons renamed, new XLSX button, new Retrieved Context section |
| `pyproject.toml` | Edit — `openpyxl>=3.1,<4` added to `[project.dependencies]` |
| `tests/unit/detail/test_view.py` | Edit — new test cases for source extraction, CSV/JSON/XLSX builders |
| `tests/integration/test_detail_ui.py` | Edit — new integration test for XLSX route |

---

## Constitution Check

Constitution template is unpopulated (placeholder only). No project-specific gates defined.  
**Standard checks**:
- No passwords or secrets in any new output path — sources contain `url`, `title`, `chunk`, `scope`, `documentId` only; no auth fields ✓  
- No new DB writes — read-only projection ✓  
- Existing CSV/JSON routes unchanged in behaviour beyond column additions ✓  
- Gate: **PASS**

---

## Phase 0 — Research (complete)

See `research.md`. All decisions resolved:

| Item | Decision |
|---|---|
| R1 — Source path | `contract["chatbotResponse"]["metadata"]["sources"]` |
| R2 — `openpyxl` version | `>=3.1,<4`; `BytesIO` streaming |
| R3 — Chunk truncation | 200-char `chunk_short` + `<details>/<summary>` in template |
| R4 — CSV column placement | Append `sourceCount`, `retrievedSources` as last two columns |
| R5 — Sheet 3 dictionary | Static; 11 Sheet-1 columns + 9 Sheet-2 columns + verdict table |
| R6 — Zero-source handling | `source_count = 0`; explicit "No context retrieved" in UI |
| R7 — Graceful degradation | `.get()` chaining + `isinstance` guard; never raises |
| R8 — Button labels | PBI Compatible CSV / PBI Compatible XLSX / JSON Download |
| R9 — Migration plan impact | Two one-line additions to Angular migration plan at Phase 1 |

---

## Phase 1 — Design Artifacts (complete)

- `data-model.md` — projection shapes for `row_view()`, CSV, JSON, XLSX
- `contracts/routes.md` — route contracts, template diff, Angular forward-compatibility notes

---

## Implementation Tasks

### Task 1 — Add `openpyxl` dependency

**File**: `pyproject.toml`  
**Change**: Add `"openpyxl>=3.1,<4"` to `[project.dependencies]`.  
**Verify**: `pip install -e ".[dev]"` (or `uv sync`) succeeds; `import openpyxl` passes.  
**Effort**: 5 min.

---

### Task 2 — Extend `row_view()` with source projection

**File**: `src/harness/ui/detail/view.py`  
**Function**: `row_view()` — currently line 132.

Add a helper at module level (near `_truncate`):

```python
def _extract_sources(contract: dict | None) -> list[dict]:
    raw = (
        (contract or {})
        .get("chatbotResponse", {})
        .get("metadata", {})
        .get("sources") or []
    )
    if not isinstance(raw, list):
        return []
    result = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        chunk = s.get("chunk") or ""
        result.append({
            "url": s.get("url") or "",
            "title": s.get("title") or "",
            "chunk": chunk,
            "chunk_short": chunk[:_TRUNCATE] + "…" if len(chunk) > _TRUNCATE else chunk,
            "scope": s.get("scope") or "",
            "documentId": s.get("documentId") or "",
        })
    return result
```

In `row_view()`, after the `contract` extraction, add:

```python
sources = _extract_sources(contract)
```

Add to the returned dict:

```python
"source_count": len(sources),
"sources": sources,
```

**Tests** (`tests/unit/detail/test_view.py`):
- Contract with `metadata.sources` populated → `source_count` correct, all five fields present
- Contract with `metadata.sources = []` → `source_count = 0`, `sources = []`
- Contract with `metadata` absent → `source_count = 0`, `sources = []`
- Contract with `metadata.sources` as a non-list string → `sources = []` (R7 guard)
- `chunk` exactly 200 chars → `chunk_short == chunk` (no ellipsis)
- `chunk` 201 chars → `chunk_short` ends with `"…"`, length 201

---

### Task 3 — Extend `results_csv_builder()` with source columns

**File**: `src/harness/ui/detail/view.py`  
**Function**: `results_csv_builder()` — currently line 254.

Add `import json` is already present. Update:

1. Header row — append `"sourceCount"`, `"retrievedSources"`:
```python
writer.writerow([
    "utteranceText", "testId", "utteranceIntent", "chatbotResponse", "overallVerdict",
    "parameterName", "score", "verdict", "reasoning",
    "sourceCount", "retrievedSources",
])
```

2. Extract sources once per utterance (before the scores loop):
```python
sources = _extract_sources(result.normalized_contract if result else None)
source_count = len(sources)
retrieved_sources_json = json.dumps(
    [{"url": s["url"], "title": s["title"], "chunk": s["chunk"],
      "scope": s["scope"], "documentId": s["documentId"]}
     for s in sources],
    ensure_ascii=False,
)
```

3. Append to each row (no-scores case and scores loop):
```python
# no-scores row
writer.writerow([..., source_count, retrieved_sources_json])
# each score row
writer.writerow([..., source_count, retrieved_sources_json])
```

**Tests**:
- Utterance with 2 sources → each row has `sourceCount = 2`; `retrievedSources` parses as JSON list of 2 objects
- Utterance with no sources → `sourceCount = 0`, `retrievedSources = "[]"`
- `chunk` field preserved verbatim (multi-line, non-ASCII)

---

### Task 4 — Extend `results_json_builder()` with `sources` key

**File**: `src/harness/ui/detail/view.py`  
**Function**: `results_json_builder()` — currently line 297.

Extract sources once per utterance:
```python
sources = _extract_sources(result.normalized_contract if result else None)
```

Add to the utterance dict:
```python
"sources": [
    {"url": s["url"], "title": s["title"], "chunk": s["chunk"],
     "scope": s["scope"], "documentId": s["documentId"]}
    for s in sources
],
```

Position: after `"parameters"` key (last key — append, don't insert mid-dict).

**Tests**:
- Utterance with sources → `sources` array present; each object has all 5 fields
- Utterance with no sources → `"sources": []`
- JSON output is valid UTF-8 JSON (non-ASCII chunk text preserved)

---

### Task 5 — Add `results_xlsx_builder()`

**File**: `src/harness/ui/detail/view.py`  
**Location**: After `results_json_builder()`.

```python
def results_xlsx_builder(job: Job, utterances: list) -> tuple[str, bytes]:
    """Three-sheet XLSX: Results (long format) / Retrieved Sources / Data Dictionary."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    base = (job.source_csv_filename or f"job-{job.job_id[:8]}").rsplit(".csv", 1)[0]
    filename = f"{base}-results.xlsx"

    wb = openpyxl.Workbook()

    # ── Sheet 1: Results (long format, mirrors CSV) ──────────────────────────
    ws1 = wb.active
    ws1.title = "Results"
    headers_s1 = [
        "utteranceText", "testId", "utteranceIntent", "chatbotResponse", "overallVerdict",
        "parameterName", "score", "verdict", "reasoning",
        "sourceCount", "retrievedSources",
    ]
    ws1.append(headers_s1)
    _bold_row(ws1, 1)

    # ── Sheet 2: Retrieved Sources (one row per utterance × source) ──────────
    ws2 = wb.create_sheet("Retrieved Sources")
    headers_s2 = [
        "utteranceId", "testId", "utteranceText",
        "sourceIndex", "title", "url", "documentId", "scope", "chunk",
    ]
    ws2.append(headers_s2)
    _bold_row(ws2, 1)

    for u in utterances:
        result = u.evaluation_result
        contract = result.normalized_contract if result else None
        response_text = (contract.get("chatbotResponse") or {}).get("normalizedText") or "" if contract else ""
        overall_verdict = (result.evaluation_verdict if result else None) or ""
        intent = (result.utterance_intent if result else None) or ""
        sources = _extract_sources(contract)
        source_count = len(sources)
        retrieved_sources_json = json.dumps(
            [{"url": s["url"], "title": s["title"], "chunk": s["chunk"],
              "scope": s["scope"], "documentId": s["documentId"]}
             for s in sources],
            ensure_ascii=False,
        )

        scores = (result.evaluation_scores or []) if result else []
        if not scores:
            ws1.append([
                u.utterance_text, u.test_id or "", intent, response_text, overall_verdict,
                "", "", "", "",
                source_count, retrieved_sources_json,
            ])
        else:
            for s in scores:
                if not isinstance(s, dict):
                    continue
                ws1.append([
                    u.utterance_text, u.test_id or "", intent, response_text, overall_verdict,
                    s.get("parameter_name", ""), s.get("score", ""),
                    s.get("verdict") or "", s.get("reasoning", ""),
                    source_count, retrieved_sources_json,
                ])

        for idx, src in enumerate(sources, start=1):
            ws2.append([
                str(u.utterance_id), u.test_id or "", u.utterance_text,
                idx, src["title"], src["url"], src["documentId"], src["scope"], src["chunk"],
            ])

    # ── Sheet 3: Data Dictionary (static) ────────────────────────────────────
    ws3 = wb.create_sheet("Data Dictionary")
    _write_data_dictionary(ws3)

    # ── Column widths (best-effort auto-fit) ─────────────────────────────────
    for ws in (ws1, ws2, ws3):
        for col_cells in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col_cells), default=0)
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max_len + 4, 60)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return filename, buf.read()


def _bold_row(ws, row_num: int) -> None:
    bold = Font(bold=True)
    for cell in ws[row_num]:
        cell.font = bold


_DICT_S1 = [
    ("Column", "Type", "Description", "Allowed values"),
    ("utteranceText", "Text", "The user question sent to the chatbot", "Any UTF-8 string"),
    ("testId", "Text", "Reference ID from the uploaded CSV", "Any string"),
    ("utteranceIntent", "Text", "Intent category from the evaluator", "Evaluator-defined or blank"),
    ("chatbotResponse", "Text", "The chatbot's plain-text reply", "Any string"),
    ("overallVerdict", "Text", "Worst-case verdict for this utterance", "pass / warn / fail / blank"),
    ("parameterName", "Text", "The scoring dimension being evaluated", "Evaluator-defined"),
    ("score", "Decimal", "Numeric score for this dimension", "0.0 (worst) to 1.0 (best)"),
    ("verdict", "Text", "Verdict for this dimension", "pass / warn / fail / blank"),
    ("reasoning", "Text", "Evaluator's rationale for this score", "Any string"),
    ("sourceCount", "Integer", "Number of KB sources retrieved for this utterance", "0 or more"),
    ("retrievedSources", "JSON Text",
     "JSON array of source objects; parse in Power Query via Json.Document([retrievedSources])",
     'JSON array or "[]"'),
]

_DICT_VERDICTS = [
    ("Verdict value", "Meaning"),
    ("pass", "Score meets or exceeds the configured threshold for this dimension"),
    ("warn", "Score is below threshold but above the minimum acceptable floor — review recommended"),
    ("fail", "Score is below the minimum acceptable floor — action required"),
    ("(blank)", "Utterance errored before evaluation; no score was produced"),
]

_DICT_S2 = [
    ("Column", "Type", "Description"),
    ("utteranceId", "Text", "Internal ID — joins to Sheet 1 rows for this utterance"),
    ("testId", "Text", "Reference ID from the uploaded CSV (repeated for readability)"),
    ("utteranceText", "Text", "The user question (repeated for readability)"),
    ("sourceIndex", "Integer", "1-based position of this source in the retrieved list"),
    ("title", "Text", "KB article or document title"),
    ("url", "Text", "Direct URL to the KB article"),
    ("documentId", "Text", "Stable document identifier"),
    ("scope", "Text", "Collection or namespace this article belongs to"),
    ("chunk", "Text", "Full text passage retrieved as grounding context"),
]


def _write_data_dictionary(ws) -> None:
    from openpyxl.styles import Font, PatternFill, Alignment
    header_fill = PatternFill("solid", fgColor="DDEEFF")
    section_font = Font(bold=True, size=12)

    ws.append(["Sheet 1 — Results: Column Definitions"])
    ws.cell(ws.max_row, 1).font = section_font
    ws.append([])
    for row in _DICT_S1:
        ws.append(list(row))
        if row[0] == "Column":
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
                cell.fill = header_fill

    ws.append([])
    ws.append(["Verdict Value Definitions"])
    ws.cell(ws.max_row, 1).font = section_font
    ws.append([])
    for row in _DICT_VERDICTS:
        ws.append(list(row))
        if row[0] == "Verdict value":
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
                cell.fill = header_fill

    ws.append([])
    ws.append(["Sheet 2 — Retrieved Sources: Column Definitions"])
    ws.cell(ws.max_row, 1).font = section_font
    ws.append([])
    for row in _DICT_S2:
        ws.append(list(row))
        if row[0] == "Column":
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
                cell.fill = header_fill
```

**Tests**:
- `results_xlsx_builder()` returns `(str, bytes)` where bytes is a valid XLSX (load with `openpyxl.load_workbook(BytesIO(body))`)
- Sheet names are exactly `["Results", "Retrieved Sources", "Data Dictionary"]`
- Sheet 1 row count = sum of score rows (or 1 per scoreless utterance)
- Sheet 2 row count = sum of source counts across all utterances (header excluded)
- Sheet 3 first cell = "Sheet 1 — Results: Column Definitions"
- Utterance with zero sources → no rows for it in Sheet 2; `sourceCount = 0` in Sheet 1
- Filename ends with `-results.xlsx`

---

### Task 6 — Add XLSX route to `routes.py`

**File**: `src/harness/ui/detail/routes.py`  
**Location**: After the `download_results_json` route (currently ~line 267).

Import `results_xlsx_builder` alongside the existing imports from `view`. Add:

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

**Tests** (`tests/integration/test_detail_ui.py`):
- Terminal job → 200, `Content-Type` contains `spreadsheetml`, `Content-Disposition` contains `.xlsx`
- Non-terminal job → 404
- Non-existent job → 404
- Response body is a valid XLSX (parse with `openpyxl.load_workbook(BytesIO(response.content))`)

---

### Task 7 — Update `detail/index.html` template

**File**: `src/harness/ui/detail/templates/detail/index.html`

**Change 1** — rename download buttons and add XLSX (lines ~69–78).  
See `contracts/routes.md` for exact before/after diff.

**Change 2** — add Retrieved Context section in the expand/trace panel.  
Insert before the `{% for label, artifact in [...] %}` loop (~line 577).  
See `contracts/routes.md` for the full HTML block.

**Verification** (manual + automated):
- Run the app locally; open a completed job; expand any row → "Retrieved Context" section visible
- Row with sources → count badge shows correct number; table renders title (hyperlinked), scope, documentId, chunk
- Row with no sources → "No context retrieved" shown explicitly
- Chunk > 200 chars → `<details>/<summary>` with truncated summary and full text on expand
- Download buttons show new labels in both terminal and non-terminal states

---

## Test Coverage Summary

| Test file | New test cases |
|---|---|
| `tests/unit/detail/test_view.py` | `_extract_sources` (6 cases), `row_view` source keys (2), CSV builder source columns (3), JSON builder sources key (3), XLSX builder (7) |
| `tests/integration/test_detail_ui.py` | XLSX route (4 cases) |

---

## Dependency Update

`pyproject.toml` — add to `[project.dependencies]`:
```toml
"openpyxl>=3.1,<4",
```

Lock file update: run `uv lock` (or `pip-compile`) after adding. Commit `pyproject.toml` and the updated lock file together.

---

## Angular Migration Plan Touch Points

When implementing Phase 1 of `docs/plans/plan-angular21-azure-functions-migration.md`:

1. `GET /api/v1/jobs/{id}/export` (plan line 146): add `xlsx` to `format` values → `format=csv|json|xlsx`
2. `JobService.export()` (plan line 604): add `'xlsx'` to type union → `format: 'csv' | 'json' | 'xlsx'`

No other Angular changes. `ExportService.downloadBlob()` already handles binary Blob responses.

---

## Effort Estimate

| Task | Effort |
|---|---|
| Task 1 — `openpyxl` dep | 5 min |
| Task 2 — `row_view()` extension | 30 min |
| Task 3 — CSV builder | 20 min |
| Task 4 — JSON builder | 15 min |
| Task 5 — XLSX builder | 60 min |
| Task 6 — XLSX route | 15 min |
| Task 7 — Template | 30 min |
| Tests | 60 min |
| **Total** | **~3.5 hours** |
