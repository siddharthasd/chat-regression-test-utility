# Contract: Evaluator Wire Protocol (v1)

**Stability**: Stable contract every evaluator service must honor. Single-shot per row (FR-001). Symmetric with the connector wire protocol (`007`).

---

## Request

`POST <endpoint_url>`, `Content-Type: application/json`, body = the **Standard Evaluation Contract instance verbatim** (the connector's output for the row; `006`). No harness-specific wrapping fields. The per-row CSV password is never included (FR-017). Auth header per the registration's mode (FR-007; identical to `007`).

The harness issues at most one request per row, serial within a job (FR-021), never retries (FR-006), and **never caches/dedups** (FR-018).

## Success Response

- HTTP `200`, `Content-Type: application/json`, body = `EvaluationResult` with the six required fields:
  `utteranceId`, `evaluationAgentId`, `evaluationTimestamp` (ISO-8601), `evaluationScores` (array of `{parameter_name, score, reasoning}`), `evaluationVerdict` (`pass`/`fail`/`warn`), `metadata` (object). No top-level `reasoning`.

## Harness post-response handling

- **Hard reject** → `evaluator_result` when the body fails FR-005b (missing/wrong-type field, `utteranceId` ≠ input, bad verdict, bad scores entry, bad timestamp, or non-JSON).
- **Soft warning** (not a failure): emitted `parameter_name`s outside the registration's declared dimensions → recorded in `harnessAnnotations.unexpected_score_dimensions`; the result is persisted unchanged.
- **`evaluationAgentId` mismatch**: persisted as-is (evaluator's self-id is authoritative), logged as a warning — does NOT fail the row.

## Failure Categorization (FR-006a)

| What the harness observes | `errorStage` | `errorDetails` |
|---|---|---|
| timeout / connection / DNS / TLS | `evaluator_transport` | "timeout exceeded" / transport error |
| HTTP status ≠ 2xx | `evaluator_response` | truncated response body |
| 2xx but not JSON / fails FR-005b | `evaluator_result` | naming the specific failed check + offending value |
| credential decrypt fails (pre-send) | `evaluator_auth` | "machine-local key missing or wrong" |

## Non-determinism (FR-018-020)

The same contract submitted twice MAY yield different scores/reasoning/verdict. The harness preserves both verbatim; it never normalizes, merges, or caches.
