# Quickstart: Job Creation & Configuration Wizard (Module 9)

**Date**: 2026-06-04

## Prerequisites
```powershell
python -m pip install -e ".[dev]"
```

## 1. Run the wizard tests
```powershell
python -m pytest tests/integration/test_wizard_ui.py -v
```
Expect: happy-path create→start, resume-at-lowest-incomplete-step, free Back/Next navigation, CSV validation gate, empty-registry affordance, archived-selection re-select, Start rollback, and no-secret-rendered all pass.

## 2. Drive it in a browser
```powershell
$env:FLASK_APP = "harness.ui:create_app"
python -m flask run
```
- Open `http://127.0.0.1:5000/jobs/new`.
- **Step 1**: name the job → Next (a Draft Job is created, `created_by` auto-stamped from your OS user).
- **Step 2**: choose a CSV → Next. Invalid CSV shows per-row errors and Next stays disabled; valid CSV shows utterance + distinct-testId counts.
- **Step 3**: pick a registered connector (or follow the link to register one if the list is empty). If the connector requires per-row passwords and your CSV had none, you're sent back to Step 2 to re-upload.
- **Step 4**: pick a registered evaluator (description + scoring dimensions shown).
- **Step 5**: review (credentials masked) → **Start Job** → you land on the confirmation page; the job is `queued` and the engine has been signaled.

## 3. Resume a Draft
Start a job, complete Steps 1–2, close the tab. Re-open `http://127.0.0.1:5000/jobs/<id>` → the wizard reopens at Step 3 with Steps 1–2 pre-filled.

## 4. No secrets in the rendered page (FR-020 / SC)
Register a connector with a distinctive bearer token, build a job through Step 5, and confirm the token string is absent from the Step 5 HTML (only the auth *mode* label shows).

## 5. Lint
```powershell
python -m ruff check src tests
```
