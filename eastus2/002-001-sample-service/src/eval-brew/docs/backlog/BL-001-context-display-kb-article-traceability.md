# BL-001 — Context Display: KB Article Traceability in Failing Query Results

**Created:** 2026-08-07
**Updated:** 2026-08-07
**Status:** Specced — ready for planning
**Area:** Results UI / Evaluation Output / Export
**Stakeholders:** QA Engineers, KB Content Authors, HR SMEs

---

## Problem Statement

When a query fails evaluation, the results output does not surface which FAQ/KB articles
were matched and retrieved during that query's execution. Without this traceability, the
team cannot distinguish between three fundamentally different root causes:

| Root cause | Symptom | Remediation |
|---|---|---|
| Missing KB article | No article exists covering this query | Author a new article |
| Retrieval mismatch | A relevant article exists but was not retrieved | Tune retrieval (embeddings, similarity threshold, chunking) |
| Incorrect keyword tagging | Article was retrieved but tagged with wrong intents | Fix metadata/tags on the existing article |

All three failure modes currently produce an identical-looking result row — a `fail`
verdict with no context. Remediation is therefore guesswork: teams either author
duplicate articles (treating retrieval failures as content gaps) or retune retrieval
(when the real fix is a missing article).

---

## Resolution Decision

**Option D — surface what is already in the contract.** No contract extension, no
evaluator output change, no harness-side retrieval call. The connector already populates
`chatbotResponse.metadata.sources` in every row, and the full `normalized_contract` JSON
is already persisted in the `evaluation_result` table. This is a read and render change
only.

---

## Data Shape

Sources live at:

```
normalized_contract["chatbotResponse"]["metadata"]["sources"]  →  array
```

Each source object in the array:

| Field | Type | Description |
|---|---|---|
| `url` | string | Direct link to the KB article or document |
| `title` | string | Human-readable article or document title |
| `chunk` | string | The text passage retrieved as grounding context |
| `scope` | string | Scope / collection / namespace the article belongs to |
| `documentId` | string | Stable identifier for the source document |

The array is absent or empty when the connector retrieved no context. Both cases are
treated as "no context retrieved" and must be signalled explicitly (not silently blank).

---

## Current Behaviour

- The results detail view and CSV/JSON exports show verdict and per-dimension scores only.
- `chatbotResponse.metadata` is stored but never rendered for end users.
- There is no display of retrieved KB articles or chunks anywhere in the product.

---

## Desired Behaviour

### UI — Results Detail / Expand Panel

In the per-row expand panel (`src/harness/ui/detail/routes.py`, rendered via
`detail/index.html`):

- Show a **"Retrieved Context" section** within the expand panel for every row
  (pass, warn, and fail — not only failures, since confirmed passes are equally
  informative for KB owners).
- Display a **count badge** before expanding: e.g., "3 sources retrieved".
- Render sources as a **table** with columns: Title (hyperlinked via `url`),
  Scope (badge), Document ID, and Chunk (truncated to ~200 chars with a
  "Show full chunk" toggle).
- When `sources` is absent or an empty array, render an explicit
  **"No context retrieved"** state — not an empty list, not a blank section.
  This zero-source state is the primary signal for a content gap.

### Downloads — Three export actions replace the current single CSV download

| Action label | Format | Sources handling |
|---|---|---|
| **PBI Compatible CSV Download** | `.csv` (renamed from current) | `sourceCount` + `retrievedSources` JSON-stringified column (all five fields including `chunk`) |
| **PBI Compatible XLSX Download** | `.xlsx` (new) | Sources expanded into a second sheet; see below |
| **JSON Download** | `.json` (unchanged label) | `sources` array added as a first-class field on each utterance object |

#### PBI Compatible CSV Download

Adds two columns to the existing long-format rows (one row per utterance × dimension):

| New column | Content |
|---|---|
| `sourceCount` | Integer — number of sources retrieved; `0` when none |
| `retrievedSources` | JSON-stringified array of source objects (`url`, `title`, `chunk`, `scope`, `documentId`); empty JSON array `[]` when none |

`chunk` is included in full. Power BI and Excel can parse the JSON string from a cell
using Power Query's `Json.Document()` — this is the intended consumption pattern.

#### PBI Compatible XLSX Download (new)

A multi-sheet Excel workbook:

**Sheet 1 — Results** (mirrors the CSV long format, one row per utterance × dimension)

Same columns as the CSV download. `retrievedSources` column contains the JSON-stringified
array, identical to the CSV. `sourceCount` column included.

**Sheet 2 — Retrieved Sources** (new — one row per utterance × source)

Provides the sources expanded into individual rows for reviewers who prefer a flat table
without JSON parsing:

| Column | Content |
|---|---|
| `utteranceId` | Foreign key back to Sheet 1 |
| `testId` | Test case reference from the uploaded CSV |
| `utteranceText` | The user question (repeated for readability) |
| `sourceIndex` | 1-based position of this source in the retrieved list |
| `title` | Source article title |
| `url` | Source article URL |
| `documentId` | Stable document identifier |
| `scope` | Collection / namespace |
| `chunk` | Full retrieved text chunk |

When a row has zero sources, it does **not** appear in Sheet 2 — zero sources is
signalled by `sourceCount = 0` in Sheet 1.

**Sheet 3 — Data Dictionary** (new — static reference)

Defines every column in Sheet 1 and Sheet 2 with description, type, and allowed values.
Includes definitions for `pass` / `warn` / `fail` verdicts.

---

## Implementation Touch Points

No database migration. No contract extension. All changes are read-and-render.

| File | Change |
|---|---|
| `src/harness/ui/detail/view.py` — `row_view()` ~line 132 | Extract `sources` from `normalized_contract["chatbotResponse"]["metadata"]["sources"]`; default to `[]`; add `source_count` and `sources` to the returned dict |
| `src/harness/ui/detail/templates/detail/index.html` | Add "Retrieved Context" section to the expand panel; render sources table; handle zero-source state |
| `src/harness/ui/detail/view.py` — `results_csv_builder()` ~line 254 | Add `sourceCount` and `retrievedSources` (JSON-stringified) columns to existing output; rename download label to "PBI Compatible CSV Download" |
| `src/harness/ui/detail/view.py` — `results_json_builder()` ~line 297 | Add `sources` array directly to each utterance object |
| `src/harness/ui/detail/routes.py` ~line 247 | Add new route `GET /jobs/{job_id}/download-results.xlsx`; wire to new `results_xlsx_builder()` |
| `src/harness/ui/detail/view.py` (new function) | `results_xlsx_builder()` — generates multi-sheet workbook using `openpyxl`; Sheet 1 mirrors CSV; Sheet 2 is the per-source expanded rows; Sheet 3 is data dictionary |
| `src/harness/ui/detail/templates/detail/index.html` | Update download button labels; add XLSX download button alongside CSV and JSON buttons |

---

## Acceptance Criteria

- [ ] Every result row's expand panel shows a "Retrieved Context" section.
- [ ] The section displays a count badge ("N sources retrieved") before the table is
      expanded.
- [ ] Each source renders as a table row: title (hyperlinked), scope badge, documentId,
      truncated chunk with "Show full" toggle.
- [ ] When `sources` is absent or empty, the section shows "No context retrieved" —
      not a blank or missing section.
- [ ] The CSV download is labelled "PBI Compatible CSV Download" and includes
      `sourceCount` (int) and `retrievedSources` (JSON string) columns.
- [ ] The XLSX download is labelled "PBI Compatible XLSX Download" and produces a
      three-sheet workbook (Results, Retrieved Sources, Data Dictionary).
- [ ] Sheet 2 (Retrieved Sources) has one row per utterance × source, with full
      `chunk` text in a dedicated column.
- [ ] Sheet 2 does not include a row for utterances with zero sources; those are
      identifiable via `sourceCount = 0` in Sheet 1.
- [ ] The JSON download includes a `sources` array as a first-class field on each
      utterance object.
- [ ] All three downloads degrade gracefully: if `sources` is absent from the contract
      (older runs, non-KB connectors), `sourceCount` is `0`, `retrievedSources` is `[]`,
      Sheet 2 has no rows for that utterance, and the UI shows "No context retrieved".
- [ ] No password or PII values appear in any exported sources field.
- [ ] `openpyxl` is added to the project dependencies; its version is pinned in
      `requirements.txt` / `pyproject.toml`.

---

## Angular + Azure Function App Migration Compatibility

This feature is **fully compatible** with the planned Angular 21 + Azure Function App
migration documented in `docs/plans/plan-angular21-azure-functions-migration.md`.

**No server-side storage required.** `openpyxl` writes to a `BytesIO` buffer in memory;
the FastAPI route returns it as a binary `Response` directly to the client. No disk
writes occur. This pattern is identical on AKS today and on the Function App after
migration. The Premium EP1 plan (locked in the migration plan) is always-on with no
execution timeout, so large workbook generation will not be killed mid-stream.

**Angular download path is already designed for this.** The migration plan defines
`ApiService.downloadBlob()` (returns `Observable<Blob>`) and `ExportService.downloadBlob()`
(creates a temporary `<a>` with an object URL and triggers a click). The XLSX download
uses this same path — no additional Angular infrastructure needed.

**Two gaps to close in the migration plan** when implementing BL-001:

| Location in migration plan | Current state | Required change |
|---|---|---|
| REST API spec `GET /api/v1/jobs/{id}/export` (line 146) | `format=csv\|json` | Add `\|xlsx` |
| `JobService.export()` TypeScript type (line 604) | `format: 'csv' \| 'json'` | Add `\| 'xlsx'` |

Both are one-line changes. The `ResultTraceExpansionComponent` (plan line 1019) is the
Angular equivalent of the current expand panel — the Retrieved Context section from this
item adds one more block to that component.

**Client-side XLSX as an alternative (not recommended):** Angular + `ExcelJS` (MIT) could
generate the workbook in the browser from a JSON export fetch. Discarded: ~300 KB bundle
addition, multi-sheet workbooks with a data dictionary are significantly more complex in
TypeScript, and large jobs with long chunk text risk blocking the browser UI thread.
Server-side `openpyxl` + BytesIO is simpler and the Function App storage constraint is
already satisfied by the in-memory pattern.

---

## Dependencies

- `openpyxl` — for XLSX generation. Confirm it is not already present in the dependency
  tree before adding.

---

## Out of Scope

- Changes to the Standard Evaluation Contract schema.
- Changes to connector or evaluator implementations.
- Adding a retrieval score / similarity score field (not present in the current
  `sources` schema; can be a follow-on if connectors start populating it).
- BL-002 summary export and BL-003 header renaming (tracked separately; the XLSX
  data dictionary in this item is a step toward BL-003 but does not replace it).
