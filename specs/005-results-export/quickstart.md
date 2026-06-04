# Quickstart: Results Export Service (Module 14)

**Date**: 2026-06-04

## Prerequisites
```powershell
python -m pip install -e ".[dev]"
```

## 1. Run the export tests
```powershell
python -m pytest tests/unit/export/ tests/integration/test_export_ui.py -v
```
Expect: builder unit tests (CSV repeated columns + JSON-stringified nesteds, JSON `{job,rows}`, zip, masked credentials/no-password, scores ordering, partial flag) + UI integration (control gating, the three formats download, draft/queued 400, deleted-job 404) all pass.

## 2. Drive it in a browser
```powershell
$env:FLASK_APP = "harness.ui:create_app"
python -m flask run
```
- Open a job with rows at `/jobs/<id>/detail`.
- Use the **Download Results** control: pick **CSV**, **JSON**, or **Both (zip)** and click — the browser downloads the file.
  - **CSV**: one rectangular table — every job-metadata field repeated on each row + the per-row trace columns; nested fields are JSON in a single quoted cell. Opens in Excel/pandas with no config.
  - **JSON**: a single object `{ "job": {...}, "rows": [...], "partial": false }`.
  - **Zip**: both of the above.
- Credentials show as `••••••••`; there is no `password` column anywhere.
- For a **running** job the file is marked partial (filename `-partial`, a `partial` column/key) and contains only the rows persisted so far.
- For a **draft/queued** job (no rows) the control is absent.

## 3. Verify no secret leaks (SC-005)
Export a job whose connector uses a bearer token, then grep the downloaded CSV and JSON for the token value — zero matches.

## 4. Lint
```powershell
python -m ruff check src tests
```
