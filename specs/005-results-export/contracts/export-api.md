# Contract: Results Export Service (Module 14)

**Date**: 2026-06-04
A reusable builder (`harness.export`) + a streaming route (`harness.ui.export_ui`). The Download Results control lives on the 004 detail page.

---

## `harness.export`

### `build_export(job, utterances, fmt, *, exported_at=None) -> (filename, mimetype, body)`
- `fmt` ∈ `FORMATS = ("csv", "json", "zip")`; unknown → treated as `csv`.
- `exported_at` defaults to `datetime.now(UTC)`.
- Returns `(filename: str, mimetype: str, body: bytes)`.
- Pure / on-demand (FR-003) — reads the passed-in ORM objects, no cache, no server-side file.

Helpers (also public for tests):
- `job_metadata(job, exported_at) -> dict` (FR-005; masked descriptors; `partial`).
- `row_record(utterance, declared_dims) -> dict` (FR-006; ordered scores; no password).

### Format bodies
- **csv** → `text/csv`; rectangular, repeated metadata columns + per-row columns; nested fields JSON-stringified per cell (FR-007/008).
- **json** → `application/json`; `{"job", "rows", "partial"}` (FR-009).
- **zip** → `application/zip`; the CSV + JSON files (FR-002).

Filename: `<slug>-results[-partial].<ext>` (`-partial` iff status ∈ {running, cancelling}, FR-010).

---

## `harness.ui.export_ui`

### `GET /jobs/<job_id>/export?format=csv|json|zip` (FR-001/004/014)
- Unknown job → `404` (FR-014 race; browser gets an error, not a partial file).
- status ∈ {draft, queued} OR `count_by_job == 0` → `400` "no rows to export" (FR-001/SC-008).
- else → `200` `Response(body, mimetype, headers={"Content-Disposition": 'attachment; filename="…"'})`.
- Always regenerated from current persisted state (FR-003/012); available indefinitely.

---

## Guarantees
- **No password** in any format (key omitted entirely — FR-006).
- **Credentials masked, never decrypted** (FR-011, SC-005) — same `mask_descriptor` as 004.
- **All persisted rows**, never the detail view's filtered subset (FR-016).
- **Partial-annotated** for non-terminal jobs in filename + inline (FR-010/SC-007).
- **Lossless** CSV round-trip incl. nested per-score `reasoning` (SC-009); **valid** single-object JSON (SC-010).
