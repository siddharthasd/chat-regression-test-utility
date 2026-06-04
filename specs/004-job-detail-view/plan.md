# Implementation Plan: Job Detail & Traceability View (Module 13)

**Branch**: `004-job-detail-view` | **Date**: 2026-06-04 | **Spec**: `specs/004-job-detail-view/spec.md`
**Base**: `foundation` (006-014 + 003 + 002, tip `f5dbd20`, 338 passed / 7 xfailed / ruff clean)

## Summary

The single-job read-and-act page. Owns **`GET /jobs/<id>/detail`** — the exact route the dashboard (002) already links to. Two regions: a **Job Metadata Panel** (snapshot config with secrets masked, aggregate counts, source-CSV download) and a **Results Table** (one row per Utterance with verdict/scores/error rendering, expand-on-click full trace, verdict/error/testId filters + search + sort). Plus the canonical job-level actions: **Cancel** (queued/running → `transition_to_cancelling`) and **Delete** (draft/failed/cancelled → cascade, back to dashboard). Live incremental updates for non-terminal jobs via polling.

This module flips the 7 credential-masking XFAILs that gate on the detail/export surfaces (the masked metadata panel + the password-free reconstructed CSV).

## Technical Context

**Language**: Python 3.11+ / Flask. **Storage**: 009 (`JobRepository`, `UtteranceRepository`, `EvaluationResultRepository`, `get_session`). **Templating**: Jinja standalone HTML (autoescape ON — the XSS-safe guarantee for evaluator-emitted scores per FR-007a). **Live updates**: vanilla-JS polling of a JSON endpoint. **No new deps.** **Testing**: pytest + Flask `test_client()` + per-test `engine.init_db(tmp)` isolation.

**Reuse**:
- 009 `JobRepository.get`, `transition_to_cancelling`, `delete` (gated to draft/failed/cancelled via `DELETABLE_STATUSES`); `UtteranceRepository.get_by_job_ordered` (each `Utterance.evaluation_result` is a one-to-one relationship → row+result join for free).
- 009 `enums`: `JobStatus`, `TERMINAL_STATUSES`, `ERROR_STAGES`.
- `harness.remote.auth._SECRET_SUBFIELDS` semantics (mask `credential`/`password`; `mode`/`headerName`/`username` are cleartext on the stored descriptor — never decrypt).
- `dashboard.view.format_timestamp` (hybrid timestamps — shared helper).

## Source layout (new)

```
src/harness/ui/detail/__init__.py
src/harness/ui/detail/routes.py     # detail page, detail.json (poll), download.csv, cancel, delete
src/harness/ui/detail/view.py       # masked metadata projection, row projection + ordered scores, filters/sort, CSV rebuild
src/harness/ui/detail/templates/detail/index.html
tests/integration/test_detail_ui.py
```
**Edits**: `ui/__init__.py` register `detail_bp`; `pyproject.toml` package-data `"harness.ui.detail"`.

## Routes (contract — see contracts/ui-routes.md)

| Method + path | Purpose |
|---|---|
| `GET /jobs/<id>/detail` | metadata panel + results table; query params `verdict`(multi), `error_only`, `test_id`(multi), `q`, `sort`, `dir` (FR-001/002/007/011-014) |
| `GET /jobs/<id>/detail.json` | live state for the poller: status/counts/row_count/terminal; 404 if deleted (FR-015/016/020) |
| `GET /jobs/<id>/download.csv` | reconstructed CSV (no password; partial marker when non-terminal) (FR-006/006a) |
| `POST /jobs/<id>/cancel` | `transition_to_cancelling` iff queued/running; 409 on race (FR-018) |
| `POST /jobs/<id>/delete` | `delete` iff draft/failed/cancelled (re-checked); redirect to dashboard (FR-019) |

## view.py (pure, testable)

- `metadata_view(job)`: all FR-003 fields; `connector_auth_descriptor`/`evaluator_auth_descriptor` passed through `mask_descriptor` (credential/password → `••••••••`, keep mode/headerName/username); status_label/badge (reuse dashboard scheme); timestamps via `format_timestamp`; counts are job-level (FR-003, never filtered).
- `row_view(utterance, declared_dims)`: rowIndex, testId, utterance_text (+truncated), chatbot_response_text (from `normalized_contract.chatbotResponse.normalizedText`), verdict + verdict_badge, `scores_cells` (ordered by `declared_dims`, then unexpected appended; "awaiting" when no result, "—" when failed/null), error_status, error_stage, `has_unexpected_dims` (from `harness_annotations.unexpected_score_dimensions`), and the expand artifacts (raw_chatbot_response, normalized_contract, verdict/scores/metadata/timestamp, harness_annotations, error_status/stage/details). Password is never in the projection.
- `apply_filters(rows, verdicts, error_only, test_ids, q)`: AND; `q` matches utterance_text OR chatbot_response_text only (FR-013/014).
- `sort_rows(rows, sort, dir)`: any column except scores (FR-011); verdict order `fail` > `warn` > `pass`.
- `reconstruct_csv(job, utterances) -> (filename, text)`: header `utteranceText,testId,<extra cols>` (no password); `-reconstructed.csv`, plus `-partial` + inline `# status / rows` marker when non-terminal (FR-006/006a, SC-009).
- `mask_descriptor(descriptor) -> dict`.

## Live updates (FR-015/016/020)

`detail.json` returns `{status, status_label, badge_class, total, processed, failed, row_count, terminal}`; 404 when the job is gone. The page polls every 3 s: update the panel badge + counters; if `row_count` grew, reload the page (preserving query params) to pull new server-rendered rows; on 404 redirect to `/` with a notice; stop polling when terminal. Tested surface = the JSON endpoint; the reload-on-growth is the progressive enhancement.

## Cancel / Delete gating (FR-018/019, SC-006/007)

Cancel control shown iff status ∈ {queued, running}; `POST /cancel` re-reads in-txn and calls `transition_to_cancelling`, catching `InvalidTransitionError` → 409 actionable message (race). Delete control shown iff status ∈ {draft, failed, cancelled}; `POST /delete` re-checks and calls `delete` (cascade) → redirect to the dashboard; `completed`/`queued`/`running`/`cancelling` never show delete.

## Constitution Check
Harness premises only (single-user, no auth). No new deps. **Secrets never rendered** — `mask_descriptor` + autoescape; the masked panel + password-free CSV are exactly what the 7 credential-masking XFAILs assert. Gate: **PASS**.

## Phase 0 / 1 outputs
- `research.md` — R1–R9 (route ownership, row+result join, secret masking, ordered scores + annotations, filters/sort, reconstructed CSV, live polling + delete-elsewhere, cancel/delete gating, XSS-safe rendering).
- `data-model.md` — metadata + row projections, masking rules, CSV shape, JSON shape, gating table.
- `contracts/ui-routes.md` — routes + params + responses.
- `quickstart.md` — seed + walkthrough.
- CLAUDE.md SPECKIT marker → `specs/004-job-detail-view/plan.md`.
