# Specification Quality Checklist: Evaluation Agent Framework (Module 7)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-29
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Pre-spec decisions resolved before writing (documented in `Clarifications`):
  1. **Scores shape** = hybrid (Q1). Parent `FR-008a`'s standardized `{parameter_name, score, reasoning}` array shape is preserved unchanged; agents additionally declare their scoring dimensions upfront in registry metadata. The wizard, detail view, and export all get the benefit of upfront declaration without breaking the parent's existing structure decision. No parent amendment needed.
  2. **Verdict enum** = closed three-value (Q2). `verdict` MUST be exactly `"pass"` / `"fail"` / `"warn"`. `warn` is optional for an agent to use; if used, the string MUST be exactly `"warn"`. Matches the 004 detail-view precedent for color-coding (`fail > warn > pass` sort order).
- Auto-applied (precedent / spec discipline):
  - **No `createdBy` anywhere** — single-user precedent.
  - **API keys / config-level secrets** handled by the same machine-local symmetric encryption utility introduced in Module 4 (`specs/007-connector-framework` → `FR-015`–`FR-019`) and formalized at parent level by `FR-023a`. No new encryption utility, no parent amendment.
  - **Per-job concurrency** = framework serializes `evaluate()` per agent within a job (`FR-019`); pins parent's "max in-flight per job" tuning to 1 in v1, consistent with Module 4's `FR-007a`.
  - **No init/teardown methods** — the user's input lists only `evaluate()`; respected. Agents manage internal state via lazy-init / internal caching. Documented in `FR-006` and Assumptions.
  - **MockEvaluationAgent shipped by default** — mirror of MockConnector pattern.
  - **Module numbering** — your "Module 7" maps to our `008-` directory by the same convention as Module 4 → `007-`.
- Non-determinism guarantee (`FR-014`–`FR-016`, `SC-005`, `SC-006`) is explicit and verifiable. MockEvaluationAgent's randomization (`FR-025`) is constructed to exercise the guarantee by default — running the bundled mock in any end-to-end test of the harness exercises the no-cache rule by construction.
- Soft-vs-hard validation policy on scores entries:
  - **Soft** when entry's `parameter_name` is not in the agent's declared dimensions (persisted + annotated; row not failed).
  - **Hard** when entry's structural shape (the `{parameter_name, score, reasoning}` triple) is missing or wrong types (row failed with stage `evaluation`).
  - This balances "robust to evaluator drift" against "catches genuine producer bugs". Documented in `FR-005` and the edge-case bullets.
- Closed verdict enum is enforced strictly (`FR-004`): any non-enum verdict is a hard failure with stage `evaluation`. No silent canonicalization (`"Pass"` becoming `"pass"`); agents are responsible for emitting exactly the canonical string.
- No `[NEEDS CLARIFICATION]` markers emitted; both genuine pre-spec ambiguities resolved before writing.
- No parent-spec amendments needed this round. The Module 7 spec inherits cleanly from Modules 4 and 6 and from parent `FR-008a` / `FR-023a` which were already in place.
- **Re-validated 2026-05-29 (Round 2)** after `/speckit-clarify` session (1 Q accepted, loop stopped early — remaining items are plan-level): the harness's soft-warning annotation block lives in a new top-level `harnessAnnotations` object on the persisted EvaluationResult, distinct from the agent's `metadata` field (new `FR-005a` defines the block; `FR-005` updated to point at it; edge case bullet updated for accuracy; entity description updated). Also tightened the hard-validation enumeration to explicitly list the `utteranceId` / `evaluationAgentId` echo checks and the timestamp / scores-entry / verdict structural checks (new `FR-005b`). All 16 checklist items remain passing; no regressions.
