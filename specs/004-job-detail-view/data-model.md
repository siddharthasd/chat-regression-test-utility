# Phase 1 Data Model: Job Detail & Traceability View (Module 13)

**Date**: 2026-06-04 | **Plan**: `specs/004-job-detail-view/plan.md`

No new entity — projects one `Job` + its `Utterance`/`EvaluationResult` rows (009). No new repo methods needed.

---

## 1. Metadata panel projection (`view.metadata_view(job)`) — FR-003

Job-level fields (counts NEVER filtered): `job_name`, `description`, `status` + `status_label` (+"Completed with errors" when `completed and failed>0`) + `badge_class`, `created_by`, `created_at`/`started_at`/`completed_at` (hybrid, blank when null), `harness_version`, `error_details` (only when failed), `connector_name` (+`connector_id` secondary), `connector_endpoint_url`, **`connector_auth_descriptor` → `mask_descriptor`**, `connector_timeout_seconds`, `connector_expects_per_row_password`, `evaluation_agent_name` (+`evaluation_agent_id`), `evaluator_endpoint_url`, **`evaluator_auth_descriptor` → `mask_descriptor`**, `evaluator_timeout_seconds`, `evaluator_declared_scoring_dimensions` (ordered list), `source_csv_filename`, `total_utterance_count`, `processed_count`, `failed_count`.

`mask_descriptor(d)`: copy; `credential`/`password` → `"••••••••"` if present; keep `mode`/`headerName`/`username`. Never decrypt (SC-003).

## 2. Results-table row projection (`view.row_view(utterance, declared_dims)`) — FR-007/008

| Field | Source |
|---|---|
| `row_index`, `test_id` | Utterance |
| `utterance_text` (+`utterance_text_short`) | Utterance |
| `chatbot_response` (+short) | `result.normalized_contract.chatbotResponse.normalizedText` (None if no contract) |
| `verdict` / `verdict_badge` | `result.evaluation_verdict` (pass/fail/warn) |
| `scores_cells` | ordered by `declared_dims` then unexpected; `awaiting`/`—` placeholders (FR-007b) |
| `error_status` / `error_stage` | `result.error_status` / `result.error_stage` (9-value enum) |
| `has_unexpected_dims` | `result.harness_annotations.unexpected_score_dimensions` non-empty (FR-007c) |
| expand artifacts | `raw_chatbot_response`, `normalized_contract`, verdict/scores/metadata/timestamp, `harness_annotations`, error_status/stage/details |

**`password` is never projected** (FR-008). No result → all eval fields `None`, scores cells "awaiting".

## 3. Filters / sort / search — FR-011/012/013/014
- `apply_filters(rows, verdicts, error_only, test_ids, q)`: keep iff (no verdict filter or `verdict in verdicts`) AND (not error_only or `error_status=="failed"`) AND (no test_id filter or `test_id in test_ids`) AND (no `q` or `q` ⊂ utterance_text or ⊂ chatbot_response). AND-combined.
- `sort_rows(rows, sort, dir)`: any column except `scores` (no sort affordance, FR-011); verdict order `fail`>`warn`>`pass`; default `row_index` asc.
- `visible_n_of_m`: shown when any filter/search active (FR-014a).

## 4. Reconstructed CSV (`view.reconstruct_csv`) — FR-006/006a
Header: `utteranceText`, `testId`, then distinct `extra_metadata` keys (first-seen order). One line per Utterance. **No `password`.** Filename `<base>-reconstructed.csv` (+`-partial` when non-terminal); non-terminal adds an inline `# job <status>; N rows at download` comment. SC-009: data-row count == persisted Utterance count at click.

## 5. Live JSON (`GET /jobs/<id>/detail.json`) — FR-015/016/020
`{status, status_label, badge_class, total, processed, failed, row_count, terminal}`; `404` when deleted. Poller patches counts/badge, reloads on `row_count` growth, redirects on 404, stops at `terminal`.

## 6. Action gating — FR-018/019
| Control | Shown iff status ∈ | Route | Repo |
|---|---|---|---|
| Cancel | {queued, running} | `POST /jobs/<id>/cancel` | `transition_to_cancelling` (409 on race) |
| Delete | {draft, failed, cancelled} | `POST /jobs/<id>/delete` | `delete` (cascade) → dashboard |
