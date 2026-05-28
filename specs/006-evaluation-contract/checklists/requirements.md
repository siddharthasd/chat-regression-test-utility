# Specification Quality Checklist: Standard Evaluation Contract

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-28
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

- This is a data/contract spec, not a UI spec. Reads less story-driven than 002–005; "user stories" represent connector authors, evaluator authors, and the schema-evolution process rather than end testers.
- Pre-spec decisions resolved before writing (documented in `Clarifications`):
  1. **Versioning policy** — additive-only changes never bump `contractVersion`; structural changes (remove, rename, type change, semantic change, optional→required) MUST bump. (`FR-006`, `FR-007`, `SC-006`, `SC-007`.)
  2. **`utteranceId` uniqueness scope** — globally unique within the harness installation (e.g., UUID v4), harness-generated, distinct from CSV-supplied `testId`. (`FR-002`.)
- Auto-applied (precedent / spec discipline):
  - **"JSON Schema definition file + validation utility function" re-framed to behavior**, with file format and function signature treated as plan-level deliverables. The spec defines WHAT validation does and WHERE it runs, not which validator library implements it.
  - **No `password` in the contract** at any path — passwords are connector-internal authentication state, not evaluator input. The schema MUST treat `password` as a violation regardless of location. (`FR-004`.)
  - **No `createdBy` anywhere** — single-user precedent.
  - **Scope: connector → evaluator only.** The evaluator → harness output side is already partially defined in parent `FR-008a` and remains there; a symmetric "Standard Evaluation Result Contract" is a separate possible feature spec.
- The Standard Evaluation Contract is the integration seam the parent harness spec has been pointing to abstractly since 001. This spec turns the abstract entity into a concrete schema with explicit fields, types, validation behavior, and versioning rules.
- Forward-compat carve-out: `conversationContext` is required-but-`null` in v1. Connectors and evaluators MUST emit/handle `null` for this field. The field's presence (even as `null`) means a future multi-turn contract version can populate it without bumping `contractVersion` — only the structural shape inside it would need a bump.
- Extensibility carve-out: `chatbotResponse.rawPayload` and `chatbotResponse.metadata` are intentionally schema-unconstrained internally. Each connector emits whatever its target chatbot natively produces (for `rawPayload`) or whatever connector-specific telemetry it wants to expose (for `metadata`). The contract owns the path TO these fields, not the shape AT them.
- No `[NEEDS CLARIFICATION]` markers emitted. The two pre-spec decisions covered the high-impact ambiguity; remaining choices (concrete schema dialect, validator language) are decisively plan-level.
- **Re-validated 2026-05-28 (Round 2)** after `/speckit-clarify` session (2 Qs accepted, loop stopped early — remaining items are plan-level): `contractVersion` is an integer-only string (`"1"`, `"2"`, …); evaluator acceptance is exact string equality (`FR-002` rewritten); the harness bundles exactly one schema (the latest), historical schemas not retained at runtime, instances with `contractVersion` ≤ bundled validate against the bundled schema via the additive-compat guarantee, instances with `contractVersion` > bundled are rejected (new `FR-015`); all version comparisons use numeric interpretation, not lexicographic (new `FR-016`). All 16 checklist items remain passing; no regressions.
