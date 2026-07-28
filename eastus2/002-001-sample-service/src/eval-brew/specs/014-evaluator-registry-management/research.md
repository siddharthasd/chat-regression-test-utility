# Phase 0 Research: Evaluator Registry & Management (Module 14)

**Date**: 2026-06-04
**Plan**: `specs/014-evaluator-registry-management/plan.md`
**Spec**: `specs/014-evaluator-registry-management/spec.md`

Resolves the plan-level decisions. Built on `foundation` (010+009+006+007+008+013); structurally mirrors `013`.

---

## R1: UI Framework & Integration

**Decision**: A Flask **Blueprint** (`evaluator_registry`) registered in `harness.ui.create_app()`, server-rendered Jinja templates — identical pattern to `013`. Test-connection posts to a route returning an HTML fragment.

**Rationale**: Symmetry with `013`; the spec mandates structural symmetry.

---

## R2: Forms & Validation (incl. ordered dimensions)

**Decision**: Hand-rolled `parse_evaluator_form()` (no `wtforms`/CSRF — single-user localhost). Declared scoring dimensions are entered as a **newline-separated textarea** (`dimensions`): one name per line. Parsing trims each line, drops blank lines, **rejects** any entry that is empty-after-trim only if it was non-blank-but-whitespace (blank lines simply ignored), preserves order, and emits a **non-blocking duplicate warning** when names repeat (FR-007–011). `description` is **required** (vs `013`'s optional).

**Rationale**: A newline textarea preserves order and supports add/remove/reorder by editing — server-rendered, no JS framework. Drag-and-drop (FR-007) is a deferred UI nicety; order preservation (SC-011) is satisfied.

**Alternatives**: a JS dynamic-list widget (rejected — unjustified for v1); comma-separated (rejected — dimension names may contain commas per `008` edge case).

---

## R3: Form ↔ Auth Descriptor Mapping

**Decision**: Identical to `013 R3` — `none`/`bearer`/`api-key-header`/`basic` → canonical descriptor (`credential`/`password` keys) that `009` encrypts and `harness.remote.auth` consumes.

---

## R4: Edit — Credential Preservation vs Replacement

**Decision**: Identical to `013 R4` — `update()` includes `auth_descriptor` only when "Replace credential" is used or the mode changed; otherwise `009`'s repo preserves the stored ciphertext. Secrets never decrypted for display (FR-016).

---

## R5: Auth-Mode Change Discards Credential (FR-006)

**Decision**: Identical to `013 R5`.

---

## R6: Hard-Delete Gating (FR-024)

**Decision**: Add `JobRepository.count_by_evaluation_agent_id(evaluation_agent_id) -> int` (`SELECT count FROM job WHERE evaluation_agent_id = ?`). `service.hard_delete()` raises `RegistrationInUseError(id, count)` when `> 0`; else `009`'s `repo.hard_delete`. Ids never recycled (FR-025).

---

## R7: Test Connection (FR-026–030)

**Decision**: `run_test_connection(endpoint_url, decrypted_descriptor, timeout_seconds, declared_dimensions, *, client=None) -> TestConnectionResult`. It builds a **valid sample Standard Evaluation Contract** via `harness.connector.mock.build_contract("test-connection", "ping")` with `utteranceId` pinned to `"test-utt"` (FR-027), POSTs it with the auth header (`harness.remote.auth.build_auth_headers`) and `httpx` timeout, then:
- categorizes transport/timeout/non-2xx outcomes (`unreachable`/`timeout`/`http_error`/`auth_decrypt_failed`);
- for a 2xx body, validates it as an **EvaluationResult** via `harness.evaluator.validate_evaluation_result(body, expected_utterance_id="test-utt")` → `valid` or `invalid_result` (with the specific FR-005b problem, e.g. bad verdict) (FR-029);
- additionally computes `harness.evaluator.compute_harness_annotations(scores, declared_dimensions)` to **soft-warn** when emitted dimensions diverge from the form's declared list (FR-029 / `008 FR-005a`), surfaced as an informational note (not a failure).
Never persists (FR-030).

**Rationale**: Mirrors the evaluator wire protocol (`008`); reuses `008`'s validator + annotation helper and `007`'s mock contract builder — no parallel logic.

---

## R8: Dependencies & New Symbols

**Decision**: **No new runtime dependencies.** New symbols: `EvaluatorRegistryService`, `parse_evaluator_form`, `run_test_connection`, `TestConnectionResult`, `RegistrationInUseError`, `JobRepository.count_by_evaluation_agent_id`. Read API (FR-031) is `008`'s existing `EvaluatorRegistryReader` (incl. `get_declared_dimensions`) — not re-implemented.

---

*All deferred decisions resolved. Implementation can proceed directly, mirroring `013`.*
