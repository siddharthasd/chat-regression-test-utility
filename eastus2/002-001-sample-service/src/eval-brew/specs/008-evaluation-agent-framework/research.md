# Phase 0 Research: Evaluation Agent Framework (Module 7)

**Date**: 2026-06-04
**Plan**: `specs/008-evaluation-agent-framework/plan.md`
**Spec**: `specs/008-evaluation-agent-framework/spec.md`

Resolves the plan-level decisions. Built on `foundation` (010+009+006), sibling to `007`.

---

## R1: HTTP Client Library

**Decision**: `httpx>=0.27`, sync `httpx.Client` per dispatch with explicit `timeout=httpx.Timeout(timeout_seconds)`; unit-tested via `httpx.MockTransport`. Identical choice and rationale to `007 R1`.

**Alternatives**: `requests` (weaker mock seam), stdlib `urllib` (awkward timeouts) — rejected.

---

## R2: Bundled Mock Evaluator Service

**Decision**: stdlib `http.server` `ThreadingHTTPServer` bound to `127.0.0.1:<port>` (`:0` ephemeral). Launchable via `python -m harness.evaluator.mock`, `harness mock-evaluator`, or as a test child process. It reads the inbound contract, echoes its `utteranceId`, and emits a well-formed `EvaluationResult`: `evaluationScores` over an operator-supplied dimension list (`--dimensions a,b,c` / `HARNESS_MOCK_DIMENSIONS`) with **unseeded-random** `score` in `[0,1]` + short random `reasoning`; **random** `evaluationVerdict ∈ {pass,fail,warn}`; `metadata={"mock": true}` (FR-023/024). Modes via `--mode`/`HARNESS_MOCK_MODE`: `ok` / `nonconformant` (bad result body) / `status500` / `slow` / `unexpected_dims` (emit a `parameter_name` outside the declared list, FR-027).

**Rationale**: FR-022/024/026 — dependency-free, child-spawnable, observably non-deterministic by construction (drives US4/SC-005/SC-012).

**Alternatives**: Flask (heavier standalone), seeded RNG by default (would undercut the non-determinism demo) — rejected; a seed knob MAY be added later (spec assumption).

---

## R3: errorStage Mapping (FR-006a) — reuses `009.ERROR_STAGES`

| Outcome | errorStage |
|---|---|
| credential decryption fails (pre-send) | `evaluator_auth` |
| timeout / connect / DNS / TLS | `evaluator_transport` |
| non-2xx status | `evaluator_response` (truncated body in details) |
| 2xx but invalid JSON or `EvaluationResult` fails FR-005b | `evaluator_result` |
| 2xx + valid EvaluationResult | success |

---

## R4: Credential Decryption — Reuse `009`

**Decision**: Same as `007 R4` — reuse `harness.persistence.encryption.decrypt_credential` on the `credential`/`password` subfields of the snapshot's `evaluator_auth_descriptor`. On `HarnessKeyMismatchError` → `evaluator_auth` (FR-016). FR-014/015/016 are satisfied by `009`; `008` consumes them.

**Note (duplication):** the decrypt+header logic is duplicated from `007/connector/auth.py` because `008` (a sibling branch) cannot import `harness.connector`. To be extracted to a shared helper at `007`+`008` integration. See plan Complexity Tracking.

---

## R5: Auth Header Construction (FR-007)

**Decision**: `build_auth_headers(descriptor)` over a decrypted descriptor — `none`→`{}`, `bearer`→`Authorization: Bearer …`, `api-key-header`→`<headerName>: …`, `basic`→`Authorization: Basic base64(user:pass)`; unknown→`ValueError`. Behaviour identical to `007 FR-007a-d`.

---

## R6: Registry Read Facade (FR-008–013)

**Decision**: `EvaluatorRegistryReader(session)` over `009`'s `EvaluationAgentRegistrationRepository`:
- `list_active() -> list[EvaluatorListEntry]` — `(evaluation_agent_id, display_name, description, declared_scoring_dimensions)`; excludes archived (FR-009a).
- `get(evaluation_agent_id) -> EvaluationAgentRegistration | None` — full record (FR-009b).
- `get_declared_dimensions(evaluation_agent_id) -> list[str]` — convenience accessor for wizard/detail/export (FR-009c; delegates to the repo's existing `get_declared_dimensions`).

**Rationale**: distinct read surface from `014`'s write surface; the dimensions accessor (SC-011) is the one extra vs the connector reader.

---

## R7: EvaluationResult Validation (FR-003/004/005/005b)

**Decision**: `validate_evaluation_result(body, *, expected_utterance_id) -> list[str]` returning an ordered list of human-readable problems (empty ⇒ valid). Hard-reject rules (→ `evaluator_result`):
1. body is a JSON object;
2. all six required fields present with correct top-level type (`utteranceId`/`evaluationAgentId`/`evaluationTimestamp` str, `evaluationScores` list, `evaluationVerdict` str, `metadata` object);
3. `utteranceId` == `expected_utterance_id`;
4. `evaluationVerdict ∈ {"pass","fail","warn"}`;
5. each `evaluationScores` entry is an object with `parameter_name` (str), `score` (number or str), `reasoning` (str);
6. `evaluationTimestamp` parses as ISO-8601 (local `datetime.fromisoformat` after normalizing a trailing `Z`, mirroring `006`'s date-time check).

`evaluationAgentId` mismatch is **deliberately not** a hard reject (spec edge case) — persisted as-is; a warning is logged via `structlog`.

**Rationale**: FR-005b enumerates exactly these checks; collecting all problems gives an actionable detail string.

---

## R8: harnessAnnotations Derivation (FR-005/005a)

**Decision**: `compute_harness_annotations(scores, declared_dimensions) -> dict` returns `{"unexpected_score_dimensions": [names in scores' parameter_name not in declared, in first-seen order]}`. Always present with a (possibly empty) list for predictable downstream consumption. Never written by the evaluator; harness-derived only. The evaluator's `metadata` is never mutated.

---

## R9: Non-Determinism (FR-018-020) & Dependencies

**Decision**: No cache/memo/dedup layer exists between `dispatch_evaluation` and the HTTP call — every call POSTs (verified by request-count tests, SC-006). The mock's RNG is unseeded (SC-005/012). Add `httpx>=0.27` to `pyproject.toml` (same dep `007` added; union at integration). No new dev deps.

| Package | Min version | Reason |
|---|---|---|
| `httpx` | `>=0.27` | sync client, per-request timeout, `MockTransport` |

---

*All deferred decisions resolved. Implementation can proceed directly.*
