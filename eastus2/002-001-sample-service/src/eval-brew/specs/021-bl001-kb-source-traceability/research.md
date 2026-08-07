# Research: BL-001 KB Source Traceability

**Feature**: `specs/021-bl001-kb-source-traceability`  
**Date**: 2026-08-07

---

## R1 — Source data path confirmed

**Decision**: Extract from `contract["chatbotResponse"]["metadata"]["sources"]`.  
**Rationale**: Verified against `standard_evaluation_contract.schema.json` line 68 (well-known keys in `metadata`) and confirmed by the product owner. Not `chatbotResponse.sources` directly.  
**Code path**: `result.normalized_contract` is already a Python dict in memory (SQLAlchemy JSON column). Access is `(result.normalized_contract or {}).get("chatbotResponse", {}).get("metadata", {}).get("sources") or []`.  
**Alternatives considered**: Top-level `chatbotResponse.sources` (rejected — not the actual path).

---

## R2 — `openpyxl` version and streaming pattern

**Decision**: Pin `openpyxl>=3.1,<4` in `pyproject.toml`. Use `BytesIO` buffer, no disk writes.  
**Rationale**: `openpyxl` is not present in the project (confirmed via `pip show openpyxl` → not found). Version `3.1.x` is the current stable series; `<4` guards against a breaking major bump. `Workbook.save(BytesIO)` is a standard pattern for in-memory generation.  
**FastAPI return pattern**:
```python
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)
return Response(
    content=buf.read(),
    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
)
```
**Alternatives considered**: `xlsxwriter` (write-only, no cell reading, fine for generation but less familiar); `ExcelJS` client-side (rejected — bundle size, complexity, browser-thread risk).

---

## R3 — Chunk truncation pattern in Jinja2 template

**Decision**: Truncate chunk to `_TRUNCATE` (200 chars) in `row_view()` via a new `_truncate_chunk()` helper; pass both `chunk` and `chunk_short` per source. Toggle via a `<details>/<summary>` inline within the source table cell — matching the existing expand/trace pattern already in `detail/index.html`.  
**Rationale**: The existing template already uses `<details>/<summary>` for the Trace expand. Consistency requires the same pattern. No JavaScript state management needed.  
**Alternatives considered**: JavaScript onclick toggle (adds JS for a pure CSS/HTML concern); showing only first 200 chars with a "…" (non-interactive, poor UX for reviewers who need the chunk).

---

## R4 — `sourceCount` / `retrievedSources` CSV column placement

**Decision**: Append `sourceCount` and `retrievedSources` as the last two columns of the existing CSV long format. Do not insert mid-row.  
**Rationale**: Downstream Power BI / Excel consumers using column-index references would break on insertion. Appending is non-breaking for consumers reading by column name (which is the correct pattern and what Power BI does via Power Query).  
**`retrievedSources` serialisation**: `json.dumps(sources_list, ensure_ascii=False)` — a JSON array string per cell. Each source object contains all five fields: `url`, `title`, `chunk`, `scope`, `documentId`. Power Query parses this with `Json.Document([retrievedSources])`.

---

## R5 — XLSX Sheet 3 (Data Dictionary) — column definitions

**Decision**: Static content written once per workbook. Covers all columns in Sheet 1 (Results) and Sheet 2 (Retrieved Sources).  

Sheet 1 columns to document:

| Column | Type | Description | Allowed values |
|---|---|---|---|
| utteranceText | Text | The user question sent to the chatbot | Any UTF-8 string |
| testId | Text | Reference ID from the uploaded CSV | Any string |
| utteranceIntent | Text | Intent category from the evaluator | Evaluator-defined or blank |
| chatbotResponse | Text | The chatbot's plain-text reply | Any string |
| overallVerdict | Text | Worst-case verdict for this utterance | pass / warn / fail / blank |
| parameterName | Text | The scoring dimension being evaluated | Evaluator-defined |
| score | Decimal | Numeric score for this dimension | 0.0 (worst) to 1.0 (best) |
| verdict | Text | Verdict for this dimension | pass / warn / fail / blank |
| reasoning | Text | Evaluator's rationale for this score | Any string |
| sourceCount | Integer | Number of KB sources retrieved for this utterance | 0 or more |
| retrievedSources | JSON Text | JSON array of source objects; parseable via Power Query Json.Document() | JSON array or [] |

Verdict definitions:

| Value | Meaning |
|---|---|
| pass | Score meets or exceeds the configured threshold for this dimension |
| warn | Score is below threshold but above the minimum acceptable floor — review recommended |
| fail | Score is below the minimum acceptable floor — action required |
| (blank) | Utterance errored before evaluation; no score was produced |

Sheet 2 columns to document:

| Column | Type | Description |
|---|---|---|
| utteranceId | Text | Internal ID — joins to Sheet 1 rows for this utterance |
| testId | Text | Reference ID from the uploaded CSV (repeated for readability) |
| utteranceText | Text | The user question (repeated for readability) |
| sourceIndex | Integer | 1-based position of this source in the retrieved list |
| title | Text | KB article or document title |
| url | Text | Direct URL to the KB article |
| documentId | Text | Stable document identifier |
| scope | Text | Collection or namespace this article belongs to |
| chunk | Text | Full text passage retrieved as grounding context |

---

## R6 — Zero-source handling

**Decision**: When `sources` is absent, `None`, or `[]`:
- `row_view()`: `source_count = 0`, `sources = []`
- Template: renders a `<p class="text-muted small">No context retrieved</p>` block — NOT a hidden or absent section
- CSV: `sourceCount = 0`, `retrievedSources = "[]"`
- JSON: `"sources": []`
- XLSX Sheet 2: no rows emitted for that utterance (zero-source is implicit via absence from Sheet 2; `sourceCount = 0` in Sheet 1 is the explicit signal)

**Rationale**: Zero-source is the primary content-gap signal for KB owners. It must be visible, not silently blank.

---

## R7 — Graceful degradation for old runs / non-KB connectors

**Decision**: The source extraction path uses `.get()` chaining with `or []` at every level. No `KeyError` or `AttributeError` can reach the template or export builders.  
**Code pattern**:
```python
sources = (
    (result.normalized_contract or {})
    .get("chatbotResponse", {})
    .get("metadata", {})
    .get("sources") or []
)
if not isinstance(sources, list):
    sources = []
```
The `isinstance` guard handles connectors that populate `metadata.sources` with a non-list value (e.g., a string or `null`).

---

## R8 — Download button label changes and XLSX button

**Decision**: In `detail/index.html`:
- Rename `"Download CSV"` → `"PBI Compatible CSV Download"`
- Rename `"Download JSON"` → `"JSON Download"` (minor label tidy)
- Add `"PBI Compatible XLSX Download"` as a new `<a>` pointing to `/jobs/{job_id}/download-results.xlsx`
- Disabled state buttons (pre-terminal jobs) must also be updated to match new labels

**Rationale**: Label parity between the button and the downloaded file content improves stakeholder orientation. Power BI label indicates the intended downstream tool.

---

## R9 — Migration plan impact (Angular / Function App)

**Decision**: No changes to the Angular migration plan's core architecture. Two forward-compatible additions needed when Phase 1 of the migration plan executes:
1. `GET /api/v1/jobs/{id}/export` — add `format=xlsx` to the allowed values (line 146 of migration plan)
2. `JobService.export()` TypeScript type — add `'xlsx'` to the union (line 604 of migration plan)

These are one-line changes each. The `BytesIO` + `Response` pattern works identically under `AsgiFunctionApp` on Azure Function App Premium EP1. No server-side storage. No deprecation risk.
