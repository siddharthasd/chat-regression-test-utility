# Data Model: BL-001 KB Source Traceability

**No database changes.** All data is already persisted in `evaluation_result.normalized_contract` (JSON column). This document covers the projection shapes added in-process.

---

## Source Object (read from contract)

Extracted from `evaluation_result.normalized_contract["chatbotResponse"]["metadata"]["sources"]`.

| Field | Type | Notes |
|---|---|---|
| `url` | `str` | Direct link to the KB article; may be relative or absolute |
| `title` | `str` | Human-readable article title |
| `chunk` | `str` | Retrieved text passage; paragraph-length |
| `scope` | `str` | Collection / namespace / knowledge-base name |
| `documentId` | `str` | Stable document identifier |

Absent or non-list values are normalised to `[]` before any consumer sees them (R7).

---

## `row_view()` — new keys added to the returned dict

| Key | Type | Value |
|---|---|---|
| `source_count` | `int` | `len(sources)`; `0` when absent |
| `sources` | `list[dict]` | Full list; each dict has `url`, `title`, `chunk`, `chunk_short`, `scope`, `documentId` |

`chunk_short` is `chunk[:200] + "…"` when `len(chunk) > 200`, else `chunk`. Computed in `row_view()` alongside the existing `_truncate()` calls.

---

## `results_csv_builder()` — new columns (appended, no reorder)

Existing columns (unchanged):
```
utteranceText, testId, utteranceIntent, chatbotResponse, overallVerdict,
parameterName, score, verdict, reasoning
```

New columns appended:
```
sourceCount, retrievedSources
```

| Column | Type | Value |
|---|---|---|
| `sourceCount` | int | `len(sources)` |
| `retrievedSources` | JSON string | `json.dumps([{url,title,chunk,scope,documentId}, ...], ensure_ascii=False)` or `"[]"` |

---

## `results_json_builder()` — new key on each utterance object

Existing keys (unchanged):
```
utteranceText, testId, utteranceIntent, chatbotResponse,
overallVerdict, errorStatus, errorStage, parameters
```

New key appended:
```
sources
```

| Key | Type | Value |
|---|---|---|
| `sources` | `list[dict]` | Array of `{url, title, chunk, scope, documentId}`; `[]` when absent |

---

## `results_xlsx_builder()` — new function, returns `(filename: str, body: bytes)`

**Sheet 1 — Results**

One row per utterance × dimension (same structure as CSV long format). All 11 columns:
```
utteranceText, testId, utteranceIntent, chatbotResponse, overallVerdict,
parameterName, score, verdict, reasoning, sourceCount, retrievedSources
```

`retrievedSources` is the same JSON-stringified array as the CSV — Power BI Power Query reads both identically.

**Sheet 2 — Retrieved Sources**

One row per utterance × source. Zero-source utterances are absent (signalled by `sourceCount = 0` in Sheet 1).

Columns (9):
```
utteranceId, testId, utteranceText, sourceIndex, title, url, documentId, scope, chunk
```

`sourceIndex` is 1-based.

**Sheet 3 — Data Dictionary**

Static. Two sections separated by a blank row:
1. Sheet 1 column definitions (11 rows) + verdict value table (4 rows)
2. Sheet 2 column definitions (9 rows)

---

## Filename conventions

| Download | Filename pattern |
|---|---|
| CSV | `{base}-results.csv` (unchanged) |
| JSON | `{base}-results.json` (unchanged) |
| XLSX | `{base}-results.xlsx` (new) |

`base` = `job.source_csv_filename` stripped of `.csv`, or `job-{job_id[:8]}` if no CSV filename.

---

## State / guard rules (all three builders + route)

- Only available for terminal jobs (`status in {completed, failed, cancelled}`).
- Route returns HTTP 404 for non-existent job or non-terminal status (matching existing CSV/JSON route behaviour).
- All three builders degrade gracefully when `sources` is absent: `sourceCount = 0`, `retrievedSources = "[]"` / `sources = []`, Sheet 2 empty.
