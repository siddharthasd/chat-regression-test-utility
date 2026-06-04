# Quickstart: Dashboard & Job Listing (Module 12)

**Date**: 2026-06-04

## Prerequisites
```powershell
python -m pip install -e ".[dev]"
```

## 1. Run the dashboard tests
```powershell
python -m pytest tests/integration/test_dashboard_ui.py -v
```
Expect: listing + badges, empty states (no-jobs vs no-matches), filters/sort/search, completed-with-errors distinction, delete gating (failed/cancelled only), clear-terminal, the jobs.json live endpoint, and the Create-New-Job + drill-in handoffs all pass.

## 2. Drive it in a browser
```powershell
$env:FLASK_APP = "harness.ui:create_app"
python -m flask run
```
- Open `http://127.0.0.1:5000/` — the dashboard is the root page.
- With no jobs: the empty state + **Create New Job** CTA (→ the wizard).
- Seed some jobs (via the wizard, or directly), reload: every job appears as one row with a color-coded status badge, hybrid timestamps (hover for the alternate form), `processed/total`, failed count, connector, created-by, harness version.
- Use the status / connector / created-by filters, the name search, and click column headers to sort. Combine them — they AND together.
- A **completed** job with failures shows "Completed with errors"; a clean completed job does not.
- **failed/cancelled** rows show a Delete button (confirm → row gone). The top **Clear all failed and cancelled** action shows the exact count and removes them all.
- Start a long job in another tab; watch its row's badge + counters update within ~5 s without reloading; the row stops updating once terminal.

## 3. Live endpoint
`GET http://127.0.0.1:5000/dashboard/jobs.json` returns each job's current `status`/`processed`/`total`/`failed`/`terminal` — the data the page polls.

## 4. Lint
```powershell
python -m ruff check src tests
```
