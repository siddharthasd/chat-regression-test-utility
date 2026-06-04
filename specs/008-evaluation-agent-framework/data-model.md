# Phase 1 Data Model: Evaluation Agent Framework (Module 7)

**Date**: 2026-06-04
**Plan**: `specs/008-evaluation-agent-framework/plan.md`

No persisted entities (`EvaluationAgentRegistration` and the persisted `EvaluationResult` row live in `009`). This module's data model is the wire-protocol shapes and the in-memory dispatch/validation types.

---

## Input: `EvaluatorSnapshot` (frozen dataclass)

Built by the orchestrator from the Job snapshot (parent FR-023).

| Field | Type | Source |
|---|---|---|
| `evaluation_agent_id` | `str` | `Job.evaluation_agent_id` |
| `endpoint_url` | `str` | `Job.evaluator_endpoint_url` |
| `auth_descriptor` | `dict` (ciphertext) | `Job.evaluator_auth_descriptor` |
| `timeout_seconds` | `int` | `Job.evaluator_timeout_seconds` |
| `declared_scoring_dimensions` | `list[str]` | `Job.evaluator_declared_scoring_dimensions` |

## Output: `EvaluatorResult` (frozen dataclass)

| Field | Type | Notes |
|---|---|---|
| `ok` | `bool` | True iff a 2xx body passed FR-005b validation |
| `evaluation_result` | `dict \| None` | the validated EvaluationResult (evaluator-emitted) |
| `harness_annotations` | `dict \| None` | `{"unexpected_score_dimensions": [...]}` derived by the harness (FR-005a) |
| `error_stage` | `str \| None` | `evaluator_auth`/`transport`/`response`/`result` |
| `error_details` | `str \| None` | actionable detail |
| `status_code` | `int \| None` | HTTP status when received |

---

## Wire Protocol (FR-001–003)

**Request** — `POST <endpoint_url>`, `Content-Type: application/json`, body = the Standard Evaluation Contract instance **verbatim** (no wrapping; FR-002). The per-row password is NOT included (FR-017).

**Success response** — `200`, JSON object = `EvaluationResult` with the six required fields:

| Field | Type | Rule |
|---|---|---|
| `utteranceId` | str | MUST equal the input contract's `utteranceId` (FR-003) |
| `evaluationAgentId` | str | SHOULD equal the registered id; mismatch ⇒ warn (not reject) |
| `evaluationTimestamp` | str | ISO-8601 / RFC 3339 |
| `evaluationScores` | array | zero+ entries `{parameter_name: str, score: number\|str, reasoning: str}` |
| `evaluationVerdict` | str | exactly one of `pass` / `fail` / `warn` |
| `metadata` | object | evaluator-owned free-form; `{}` valid |

There is **no** top-level `reasoning` field (per-score reasoning only).

---

## Verdict Enum

`VERDICTS = {"pass", "fail", "warn"}` (closed; FR-004).

## errorStage Mapping (FR-006a) — reuses `009.ERROR_STAGES`

| Condition | `error_stage` |
|---|---|
| decrypt fails pre-send | `evaluator_auth` |
| timeout / connect / DNS / TLS | `evaluator_transport` |
| non-2xx | `evaluator_response` |
| 2xx, invalid JSON or fails FR-005b | `evaluator_result` |

## EvaluationResult Validation (FR-005b — hard reject ⇒ `evaluator_result`)

`validate_evaluation_result(body, *, expected_utterance_id) -> list[str]` (empty ⇒ valid):
1. body is a JSON object;
2. six required fields present with correct top-level types;
3. `utteranceId == expected_utterance_id`;
4. `evaluationVerdict ∈ VERDICTS`;
5. each `evaluationScores` entry is an object with `parameter_name` (str), `score` (number/str), `reasoning` (str);
6. `evaluationTimestamp` parses as ISO-8601.

(`evaluationAgentId` mismatch is **not** here — soft warning only.)

## harnessAnnotations (FR-005/005a)

`compute_harness_annotations(scores, declared_dimensions) -> {"unexpected_score_dimensions": [...]}` — emitted `parameter_name`s not in the declared list, first-seen order; empty list when aligned. Harness-derived; sibling of (never merged into) the evaluator's `metadata`.

## Registry Read Types (FR-008-013)

- `EvaluatorListEntry` (frozen): `evaluation_agent_id`, `display_name`, `description`, `declared_scoring_dimensions`.
- `get(id)` → full `009` `EvaluationAgentRegistration`.
- `get_declared_dimensions(id)` → `list[str]` (SC-011).
