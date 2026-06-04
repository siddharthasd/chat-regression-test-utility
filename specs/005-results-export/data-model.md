# Phase 1 Data Model: Results Export Service (Module 14)

**Date**: 2026-06-04 | **Plan**: `specs/005-results-export/plan.md`

No new entity — a read-time projection of one `Job` + its `Utterance`/`EvaluationResult` rows (009). No new repo methods.

---

## 1. Job-metadata block (`builder.job_metadata(job, exported_at)`) — FR-005

`jobId`, `jobName`, `description`, `createdBy`, `createdAt`, `startedAt`, `completedAt`, `status`, `harnessVersion`, `sourceCSVFilename`, `errorDetails` (only when failed), `connectorId`, `connectorName`, `connectorEndpointUrl`, **`connectorAuthDescriptor` → `mask_descriptor`**, `connectorTimeoutSeconds`, `connectorExpectsPerRowPassword`, `evaluationAgentId`, `evaluationAgentName`, `evaluatorEndpointUrl`, **`evaluatorAuthDescriptor` → `mask_descriptor`**, `evaluatorTimeoutSeconds`, `evaluatorDeclaredScoringDimensions`, `totalUtteranceCount`, `processedCount`, `failedCount`, `exportedAt`, `partial` (`status ∈ {running, cancelling}`).

`mask_descriptor`: credential/password → `••••••••`; mode/headerName/username verbatim; **never decrypt** (FR-011).

## 2. Per-row block (`builder.row_record(utterance, declared_dims)`) — FR-006

`utteranceId`, `rowIndex`, `utteranceText`, `testId`, `rawChatbotResponse`, `normalizedContract`, `evaluationVerdict`, `evaluationScores` (ordered per §3), `metadata`, `harnessAnnotations` (always present, `{}` when none), `evaluationAgentId`, `errorStatus`, `errorStage` (9-value enum), `errorDetails`, `evaluationTimestamp`.

**Never** included: `password` (key absent entirely), `userFeedback*`, top-level `reasoning`.

## 3. Scores ordering (FR-006a)
Order by `declared_dims`; entries whose `parameter_name` ∉ declared appended after, in emitted order. JSON: array order. CSV: JSON-stringified in that order.

## 4. Format shapes
| Format | Shape |
|---|---|
| **JSON** (FR-009) | `{"job": {…metadata…}, "rows": [ {…row…} ], "partial": bool}`; nested fields native (parse persisted JSON strings; `_unparseable: true` on failure) |
| **CSV** (FR-007/008) | rectangular; columns = metadata fields (repeated every row) + per-row fields; nested fields `json.dumps`-ed into one quoted cell; `partial` carried as a column |
| **zip** (FR-002) | `zipfile` with the CSV + JSON, each independently valid |

## 5. Route + gating (FR-001/014)
`GET /jobs/<id>/export?format=csv|json|zip` → 404 (job gone), 400 (status ∈ {draft, queued} or 0 rows), else stream. Filename `<slug(job_name) or job-<id8>>-results[-partial].<ext>`. `Content-Type`: `text/csv` / `application/json` / `application/zip`.

## 6. Detail-page control (FR-001/002)
004's detail route adds `can_export = row_count > 0 and status ∉ {draft, queued}`; `detail/index.html` renders a `format` select + Download Results button when true, else omits it.
