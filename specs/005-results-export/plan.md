# Implementation Plan: Results Export Service (Module 14)

**Branch**: `005-results-export` | **Date**: 2026-06-04 | **Spec**: `specs/005-results-export/spec.md`
**Base**: `foundation` (006-014 + 003 + 002 + 004, tip `67dfeb2`, 356 passed / 7 xfailed / ruff clean)

## Summary

The last module: an on-demand **results export** — every per-utterance trace + a job-level metadata block — downloadable as **CSV**, **JSON**, or **both-in-a-zip**, triggered by a **Download Results** control on the Job Detail View (004). Generated fresh on every click from the latest persisted state (no cache). Secrets masked, passwords omitted entirely, scores ordered by the snapshotted declared dimensions, partial-annotated for non-terminal jobs.

A reusable builder (`harness.export`) does the file generation; a thin streaming route serves it; the control is added to 004's existing detail page.

## Technical Context

**Language**: Python 3.11+. **Storage**: 009 read-only (`JobRepository`, `UtteranceRepository` + the `Utterance.evaluation_result` one-to-one). **Files**: stdlib `csv`, `json`, `zipfile`, `io`. **Delivery**: Flask streaming `Response` with `Content-Disposition: attachment`. **No new deps.** **Testing**: pytest (unit on the builder + Flask `test_client` integration) + per-test `engine.init_db(tmp)`.

**Reuse**:
- 009 `JobRepository.get`, `UtteranceRepository.get_by_job_ordered` / `count_by_job`.
- `harness.ui.detail.view.mask_descriptor` (identical masking to 004 FR-005 — credential/password → `••••••••`, never decrypt).
- 004's detail page hosts the control (this module edits `detail/routes.py` to pass `can_export` + `detail/index.html` to render the form).

## Source layout (new)

```
src/harness/export/__init__.py        # re-exports build_export, FORMATS
src/harness/export/builder.py         # job_metadata, row_record, build_csv/json/zip, build_export(job, utts, fmt)
src/harness/ui/export_ui/__init__.py  # exports bp
src/harness/ui/export_ui/routes.py    # GET /jobs/<id>/export?format=csv|json|zip (stream)
tests/unit/export/__init__.py
tests/unit/export/test_builder.py
tests/integration/test_export_ui.py
```
**Edits**: `ui/__init__.py` register `export_bp`; `detail/routes.py` add `can_export`; `detail/index.html` add the Download Results control. No package-data (export_ui ships no templates; the control lives in detail's template).

## Builder API (contract — see contracts/export-api.md)

```python
FORMATS = ("csv", "json", "zip")
build_export(job, utterances, fmt, *, exported_at=None) -> (filename, mimetype, body: bytes)
```
- `job_metadata(job, exported_at)` → dict (FR-005 fields; `connector_auth_descriptor`/`evaluator_auth_descriptor` via `mask_descriptor`; `exportedAt`; `partial = status in {running, cancelling}`).
- `row_record(utterance, declared_dims)` → dict (FR-006 fields; `evaluationScores` ordered by `declared_dims` then unexpected appended — FR-006a; **no password**, no `userFeedback*`, no top-level `reasoning`).
- **JSON** (FR-009): `{"job": {...}, "rows": [...], "partial": bool}`; nested fields native (parse persisted JSON strings back to structure; `_unparseable: true` sibling on failure).
- **CSV** (FR-007/008): repeated columns — every metadata field on every data row + the per-row columns; nested fields (`rawChatbotResponse`, `normalizedContract`, `evaluationScores`, `metadata`, `harnessAnnotations`) JSON-stringified into one cell (lossless, CSV-quoted). Rectangular, zero-config for pandas/Excel.
- **zip** (FR-002): both files via `zipfile`.

## Partial annotation reconciliation (FR-010 vs FR-007)

FR-010 wants an inline partial marker; FR-007 forbids skip-rows / out-of-band metadata in CSV. Reconciliation: the partial signal is carried as **regular repeated columns** — `status` (already present) + a `partial` boolean column — never a comment line, so the CSV stays rectangular. JSON gets a top-level `partial: true`. Both formats get `-partial` in the filename. (The 004 source-CSV download, which is not pandas-rectangular by contract, keeps its comment-line marker; the results export must stay rectangular.)

## Route (contract — see contracts/export-api.md)

`GET /jobs/<id>/export?format=csv|json|zip`:
- 404 if the job doesn't exist (FR-014 race).
- 400 if status ∈ {draft, queued} or `count_by_job == 0` (FR-001/SC-008).
- invalid/missing format → default `csv` (plan-level default).
- else `build_export` → `Response(body, mimetype, headers={Content-Disposition: attachment; filename=...})`.

Filename: `<slug(job_name) or job-<id8>>-results[-partial].<ext>`.

## Detail-page control (FR-001/002, edits 004)

`detail/routes.py`: add `can_export = (row_count > 0 and status not in {draft, queued})` to the render context (main + error re-render). `detail/index.html`: when `can_export`, render a small GET form to `export.export` with a `format` `<select>` (csv/json/zip) + Download Results button; otherwise omit (or a disabled note).

## Streaming (FR-013, SC-002)

Build the body and return it via Flask `Response`; for the 1,000-row target the in-memory build + send is well under 2 s. (True chunked streaming is unnecessary at this scale and complicates zip; the spec's "without buffering the entire payload" is a large-scale guard — noted as a future optimization if the row ceiling rises.)

## Constitution Check
Harness premises only. No new deps. **Passwords omitted entirely; credentials masked, never decrypted** (FR-006/011) — this is the export side of the credential-masking contract. Gate: **PASS**.

## Phase 0 / 1 outputs
- `research.md` — R1–R8 (builder vs route split, metadata/row projection, scores ordering, CSV repeated-columns + JSON-stringify, JSON nested parse, partial reconciliation, masking/no-password, control gating).
- `data-model.md` — metadata + row record fields, format shapes, gating.
- `contracts/export-api.md` — builder + route.
- `quickstart.md` — seed + download walkthrough.
- CLAUDE.md SPECKIT marker → `specs/005-results-export/plan.md`.
