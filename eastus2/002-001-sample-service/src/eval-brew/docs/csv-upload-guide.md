# Uploading a Test CSV — User Guide

This guide explains the CSV file you upload when creating a regression test job:
its required format, the validation rules, and what the harness does with it after
you upload. It is written for testers using the harness — no technical background
required.

---

## 1. What the CSV is for

When you create a job, you upload a CSV that lists the utterances (the messages) to
send to your chatbot. The harness sends each row to the chatbot connector, captures
the response, runs it through your chosen evaluation agent, and records the result —
one result per row. **Your CSV is the list of test cases for the run.**

> This guide covers the **browser wizard** (CSV upload) path. If you need to submit test
> cases programmatically — without a file upload — the harness also provides a **Headless
> Execution API** at `/api/headless` that accepts test cases as JSON and streams live
> progress back to the caller.

---

## 2. File format requirements

The harness accepts a **plain CSV file, comma-separated, saved as UTF-8**.

| Requirement | Detail |
|---|---|
| File type | `.csv` (plain text). **Not** `.xlsx`, `.xls`, or any binary spreadsheet. |
| Encoding | UTF-8 (a leading byte-order mark / BOM is fine and is stripped automatically). |
| Delimiter | Comma only. Semicolon- or tab-separated files are rejected. |
| First row | A header row naming the columns. |
| Quoting | Standard CSV quoting. Values containing commas, quotes, or line breaks are fine **if** wrapped in double quotes. |

> **Using Excel?** Excel workbooks (`.xlsx`) are **not** supported directly. In Excel,
> use **File → Save As → CSV UTF-8 (Comma delimited)** and upload that file. Note
> that on some regional settings Excel saves CSVs with semicolons — if your upload is
> rejected for the delimiter, re-save as comma-delimited.

---

## 3. Columns

Column identity comes from the **header row** (names, not positions), so columns may
appear in any order. Header names are **case-sensitive** and surrounding spaces are
trimmed (` testId ` matches `testId`).

### Required columns

| Column | Required | Description |
|---|---|---|
| `utteranceText` | Always | The message text to send to the chatbot. |
| `testId` | Always | Your identifier for the test case. Used to group/trace rows; it is **not** validated against anything and is preserved through results, the detail view, and exports. |
| `password` | **Only if** the selected connector needs a per-row password | A per-row credential forwarded to the chatbot for that row. See §5. |

### The `password` column is conditional

Whether `password` is required depends on the **connector** you select for the job
(set up by whoever registered the connector):

- **Connector needs a per-row password** → the `password` column is **required**, and
  every row must have a non-empty value.
- **Connector does not** → omit the column entirely (recommended). If you include it,
  it is ignored.

Because the connector is chosen *after* the upload step in the wizard, you may be asked
to **re-upload** your CSV if you pick a connector that needs passwords and your file
didn't include them. See §6.

### Extra columns

Any additional columns beyond the ones above are **accepted and preserved** as per-row
metadata (visible in the row's detail/expand view and in exports). Use them for notes,
expected answers, categories, etc.

---

## 4. Examples

**Minimal (connector does not need per-row passwords):**

```csv
utteranceText,testId
"What are your opening hours?",hours-001
"Cancel my order please",cancel-001
"Tell me a joke",fun-001
```

**With per-row passwords (connector requires them):**

```csv
utteranceText,testId,password
"Show my account balance",balance-001,hunter2
"Transfer $50 to savings",transfer-001,hunter2
```

**With extra metadata columns and a multi-line value:**

```csv
utteranceText,testId,expectedTopic,note
"What's the weather?",weather-001,smalltalk,baseline case
"I have a complaint about my bill.
It is too high.",billing-002,billing,"multi-line input, quoted"
```

---

## 5. How passwords are handled (important)

If your CSV includes a `password` column:

- Passwords are held **in memory only** for the duration of the run and forwarded to
  the chatbot connector one row at a time.
- Passwords are **never written to the database**, **never included in any export**,
  and **never shown** in the job detail view (you'll see the configuration's auth mode,
  but credential values are masked as `••••••••`).
- Each row's password is **discarded immediately** after that row's chatbot call
  completes.
- The original CSV file itself is **not retained** on the server. The job stores the
  parsed rows and the file's name only.

One consequence: if the harness restarts between upload and starting the job, the
in-memory passwords are gone, and you'll need to re-upload the CSV before starting.

---

## 6. Validation rules

When you upload, the harness checks the file **before** saving anything. If any check
fails, **nothing is saved** and you'll see a clear, per-issue error message; fix the
file and re-upload.

| The harness rejects the upload when… | What you'll see |
|---|---|
| The file is larger than the configured limit (default **50 MiB**) | Size-exceeded error naming the limit and your file's size (checked before the file is even read) |
| The file isn't valid UTF-8 text (e.g. you uploaded a real Excel workbook) | Encoding error |
| The file isn't comma-delimited (semicolons/tabs detected) | Unsupported-delimiter error |
| A required column is missing (`utteranceText`, `testId`, or `password` when needed) | Missing-column error naming each missing column |
| The header has duplicate column names | Duplicate-column error |
| There are no data rows (header only) | No-data-rows error |
| A row has more or fewer cells than the header | Row/column-count mismatch, naming the row number |
| A required cell is empty or only whitespace | Empty-value error, naming the row number and column |

**Accepted automatically (no action needed):**

- A leading UTF-8 BOM is stripped silently.
- Completely blank rows at the end of the file are skipped (you'll get an informational
  note saying how many were skipped).
- Quoted values with embedded commas, quotes, or line breaks are preserved exactly.
- Non-ASCII / Unicode text (accents, emoji, non-Latin scripts) is preserved exactly.

**What is *not* checked:** the harness validates **structure only** — column presence
and non-empty required values. It does **not** verify that `testId` or `password`
values are "correct" against any system. If a credential is wrong, that surfaces later
as a per-row failure when the chatbot rejects it during the run.

---

## 7. What happens after a successful upload

1. **Parsing & storage.** Each data row becomes one stored *utterance*, in file order
   (row 1, row 2, …). The job records how many utterances were created and how many
   distinct `testId` values it saw, and shows you that summary so you can sanity-check
   before continuing.
2. **Re-uploading replaces.** If you upload again to the same draft job (for example,
   after going Back in the wizard), the new file **completely replaces** the previous
   rows — there is no "append". The last upload wins.
3. **Starting the job.** When you finish the wizard and click **Start Job**, the job is
   queued and the engine begins processing rows **one at a time, in file order**:
   - send the row to the chatbot connector → capture the raw response,
   - normalize it into the standard contract,
   - send that to the evaluation agent → record the verdict and scores.
4. **Per-row failures are isolated.** If a row fails at any stage (chatbot unreachable,
   bad response, evaluator error, etc.), that single row is recorded as *failed* with
   the stage and reason, and processing **continues** with the next row. One bad row
   does not stop the run. A job that finishes with some failed rows still ends as
   *completed* (shown as "Completed with errors").
5. **Watching progress.** The dashboard and the job detail view update live as rows
   complete — you don't need to refresh.
6. **Results.** When the run finishes you can inspect every row's full trace in the
   detail view and **download the complete results** as CSV, JSON, or both (zipped).
   Exports never contain any password.

---

## 8. Quick checklist before you upload

- [ ] Saved as **CSV UTF-8**, comma-delimited (not a raw `.xlsx`).
- [ ] First row is a header with `utteranceText` and `testId` (exact spelling, any order).
- [ ] Added a `password` column **only if** your connector needs per-row credentials,
      with a value on every row.
- [ ] No empty `utteranceText`/`testId` (or `password`, when required) cells.
- [ ] Multi-line or comma-containing values are wrapped in double quotes.
- [ ] At least one data row.

---

## 9. Common pitfalls

| Symptom | Likely cause & fix |
|---|---|
| "File is not valid UTF-8" | You uploaded an `.xlsx` (or other binary). Save As → CSV UTF-8. |
| "Only comma-delimited CSV is supported" | Excel saved with semicolons (regional setting). Re-save comma-delimited, or fix the delimiter. |
| "Missing required column: password" | You selected a connector that needs per-row passwords. Add a `password` column (a value per row) and re-upload. |
| "Missing required column: testId" | Header typo or wrong case (`TestID` ≠ `testId`). Match the exact name. |
| "Row N has X columns, expected Y" | An unquoted comma or line break split a cell. Wrap that value in double quotes. |
| "Required column 'utteranceText' is empty" | A blank cell in a required column. Fill it or remove the row. |
| Job started but every row failed | Often wrong credentials or an unreachable chatbot endpoint — check the row error details in the detail view. The CSV itself was fine. |
