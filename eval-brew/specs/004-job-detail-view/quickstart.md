# Quickstart: Job Detail & Traceability View (Module 13)

**Date**: 2026-06-04

## Prerequisites
```powershell
python -m pip install -e ".[dev]"
```

## 1. Run the detail-view tests
```powershell
python -m pytest tests/integration/test_detail_ui.py -v
```
Expect: metadata panel (masked secrets), row trace expand, verdict/error/testId filters + search + sort, scores ordering + unexpected-dimension indicator, reconstructed CSV (no password, partial marker), detail.json live state, Cancel/Delete gating, and delete→dashboard all pass.

## 2. Drive it in a browser
```powershell
$env:FLASK_APP = "harness.ui:create_app"
python -m flask run
```
- From the dashboard (`/`), click any job row → you land on `/jobs/<id>/detail`.
- **Metadata panel**: name, status badge, Created By, timestamps, connector + evaluator config with credential fields shown as `••••••••`, declared scoring dimensions, source-CSV download, and Total/Processed/Failed counts.
- **Results table**: one row per utterance — verdict (color-coded), scores (in declared-dimension order), error status. Expand a row for the full input + raw response + normalized contract + evaluation result (+copy buttons). Rows whose evaluator emitted unexpected dimensions show an indicator.
- Filter by verdict / error-only / testId, search utterance+response text, sort columns (Scores has no sort).
- **Download** the reconstructed CSV — note it omits `password` and is marked reconstructed (and partial for a running job). **Note**: this route (`/jobs/<id>/download.csv`) is retired by feature 018, which replaces it with `/jobs/<id>/download-results.csv` and `/jobs/<id>/download-results.json`.
- **Cancel** (queued/running) or **Delete** (draft/failed/cancelled) — Delete returns you to the dashboard.
- Open a running job; watch counts + rows update within ~5 s without refreshing.

## 3. Lint
```powershell
python -m ruff check src tests
```
