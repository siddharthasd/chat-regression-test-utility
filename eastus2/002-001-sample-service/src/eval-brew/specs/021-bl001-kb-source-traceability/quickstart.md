# Quickstart: BL-001 KB Source Traceability

Walkthrough for verifying the feature end-to-end after implementation.

---

## Prerequisites

- Local dev server running (`uvicorn` or `func start`)
- A **completed** job in the database whose connector populated `chatbotResponse.metadata.sources` on at least some utterances
- `openpyxl` installed (`pip show openpyxl` returns a version)

---

## 1. Verify the UI expand panel

1. Navigate to any completed job → **Results** tab.
2. Expand any row (click **Trace**).
3. Confirm:
   - "Retrieved Context" section is visible above the artifact `<pre>` blocks.
   - Count badge shows "N sources retrieved".
   - If sources exist: a **Show sources** `<details>` expander is present; table renders Title (linked), Scope badge, Document ID, Chunk.
   - If `chunk` > 200 chars: clicking the chunk cell reveals the full text via an inner `<details>`.
4. Expand a row from an utterance with zero sources.
5. Confirm: "No context retrieved" text is displayed (not blank, not missing).

---

## 2. Verify PBI Compatible CSV Download

1. On the completed job detail page, click **PBI Compatible CSV Download**.
2. Open the downloaded `.csv` in Excel or a text editor.
3. Confirm:
   - The header row ends with `sourceCount,retrievedSources`.
   - Rows for utterances with sources have an integer > 0 in `sourceCount` and a JSON array string in `retrievedSources`.
   - Rows for zero-source utterances have `0` and `[]` in those columns.
4. In Excel → Data → Get Data → From Table/Range → select `retrievedSources` column → Transform → Parse JSON.
   Confirm each record expands to `url`, `title`, `chunk`, `scope`, `documentId` fields.

---

## 3. Verify PBI Compatible XLSX Download

1. Click **PBI Compatible XLSX Download**.
2. Open the downloaded `.xlsx`.
3. Check **Sheet 1 (Results)**:
   - Same structure as CSV. Last two columns: `sourceCount`, `retrievedSources`.
4. Check **Sheet 2 (Retrieved Sources)**:
   - One row per utterance × source (utterances with zero sources are absent).
   - Columns: `utteranceId`, `testId`, `utteranceText`, `sourceIndex`, `title`, `url`, `documentId`, `scope`, `chunk`.
   - `sourceIndex` is 1-based; multiple sources for one utterance appear as consecutive rows.
5. Check **Sheet 3 (Data Dictionary)**:
   - Contains "Sheet 1 — Results: Column Definitions" section with 11 column rows.
   - Contains "Verdict Value Definitions" with 4 verdict rows.
   - Contains "Sheet 2 — Retrieved Sources: Column Definitions" with 9 column rows.
6. Verify a zero-source utterance is absent from Sheet 2 but present in Sheet 1 with `sourceCount = 0`.

---

## 4. Verify JSON Download

1. Click **JSON Download**.
2. Open the downloaded `.json`.
3. Confirm each utterance object contains a `sources` key.
4. For an utterance with sources: array contains objects with `url`, `title`, `chunk`, `scope`, `documentId`.
5. For a zero-source utterance: `"sources": []`.

---

## 5. Verify graceful degradation (older jobs)

1. Use a job whose connector did **not** populate `chatbotResponse.metadata.sources` (or an older run where the field is absent).
2. Expand a row → confirm "No context retrieved" (not a crash or blank section).
3. Download CSV → `sourceCount = 0`, `retrievedSources = "[]"` for all rows.
4. Download XLSX → Sheet 2 is empty (header row only); Sheet 1 has `sourceCount = 0`.
5. Download JSON → `"sources": []` on every utterance.

---

## 6. Verify pre-terminal download buttons

1. Navigate to a job in `running` or `queued` state.
2. Confirm all three download buttons show as disabled with correct labels:
   - "PBI Compatible CSV Download" (disabled)
   - "PBI Compatible XLSX Download" (disabled)
   - "JSON Download" (disabled)
