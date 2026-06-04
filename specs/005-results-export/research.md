# Phase 0 Research: Results Export Service (Module 14)

**Date**: 2026-06-04 | **Plan**: `specs/005-results-export/plan.md`

Built on `foundation`. Stdlib-only file generation, no new deps.

---

## R1: Builder vs route split
**Decision**: a pure `harness.export.builder` (job/row projection + CSV/JSON/zip serialization) + a thin `harness.ui.export_ui` route that loads the job and streams the builder's output. The control lives on 004's detail page.
**Rationale**: the builder is unit-testable without Flask; the route is a one-liner over it; the spec frames the module as "a backend service + a UI control".

## R2: Job-metadata + per-row projection (FR-005/006)
**Decision**: `job_metadata(job, exported_at)` emits the FR-005 block (ids, names, timestamps, status, harnessVersion, masked descriptors, counts, exportedAt, partial). `row_record(utterance, declared_dims)` emits the FR-006 per-row block from `utterance.evaluation_result` (None-safe). **No `password`, no `userFeedback*`, no top-level `reasoning`.**
**Rationale**: direct projection of 009 columns; the one-to-one relationship gives row+result without a manual join (same as 004).

## R3: Scores ordering (FR-006a)
**Decision**: order `evaluationScores` by the Job's snapshotted `evaluator_declared_scoring_dimensions`; entries whose `parameter_name` is not declared (the `harnessAnnotations.unexpected_score_dimensions` ones) come after, in emitted order. Applies to the JSON array and (when present) the CSV.
**Rationale**: stable column/array order makes two exports of the same registration concatenate trivially (the spec's headline analyst workflow).

## R4: CSV shape — repeated columns + JSON-stringified nesteds (FR-007/008)
**Decision**: one rectangular table; every job-metadata field is repeated on every data row, alongside the per-row columns. Nested structured fields (`rawChatbotResponse`, `normalizedContract`, `evaluationScores`, `metadata`, `harnessAnnotations`) are `json.dumps`-ed into a single quoted cell via `csv.writer` (lossless escaping of commas/quotes/newlines).
**Rationale**: zero-config for pandas/Excel/`csv.DictReader`; JSON-in-a-cell keeps the table rectangular while preserving structure (SC-009 lossless round-trip).
**Alternatives**: one-column-per-dimension flattening (FR-006a allows it) — rejected for v1 in favor of the simpler, always-lossless JSON-stringify, which FR-008 mandates anyway.

## R5: JSON shape + nested parse (FR-009, edge case)
**Decision**: `{"job": {...}, "rows": [...], "partial": bool}`. Persisted JSON columns are already dict/list (SQLAlchemy JSON type) → emitted natively. If a value is a string that looks like JSON, attempt `json.loads`; on failure include it as the string plus an `_unparseable: true` sibling.
**Rationale**: the DB stores these as JSON columns so they deserialize to structure already; the parse-and-mark fallback covers the corrupt-value edge case.

## R6: Partial annotation reconciliation (FR-010 vs FR-007)
**Decision**: carry the partial signal as **regular repeated columns** (`status` + a `partial` boolean) — never a CSV comment line — so the table stays rectangular (FR-007). JSON gets a top-level `partial: true`. Both filenames get `-partial`. Non-terminal = status ∈ {running, cancelling}.
**Rationale**: a header-row comment would violate FR-007's no-skip-rows rule; columns satisfy "inline within the file" without breaking standard readers. (Contrast 004's source-CSV download, which is not contractually rectangular and keeps its comment marker.)

## R7: Masking + no password (FR-006/011, SC-005)
**Decision**: reuse `harness.ui.detail.view.mask_descriptor` for both auth descriptors (credential/password → `••••••••`, keep mode/headerName/username; never decrypt). The per-row block omits `password` **entirely** (not masked, not null-stubbed — the key is absent).
**Rationale**: single masking implementation shared with 004; passwords were never persisted on rows anyway, so omission is natural. This is the export side of the credential-masking contract.

## R8: Control gating + delivery (FR-001/004/014, SC-008)
**Decision**: 004's detail route computes `can_export = row_count > 0 and status not in {draft, queued}` and renders a format `<select>` + Download Results button when true. The route `GET /jobs/<id>/export?format=` returns 404 (job gone, FR-014), 400 (draft/queued or zero rows), else a Flask `Response` with `Content-Type` + `Content-Disposition: attachment`. No server-side file is written (FR-004).
**Rationale**: reuses 004's already-loaded job state for the gate; browser-native download per the spec; the 404/400 paths cover the race + empty cases.

---

*All decisions resolved. Implementation can proceed.*
