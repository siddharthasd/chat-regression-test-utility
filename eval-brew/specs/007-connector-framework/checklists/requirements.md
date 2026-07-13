# Specification Quality Checklist: Connector Framework (Module 4)

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

- Pre-spec decisions resolved before writing (documented in `Clarifications`):
  1. **Encryption scope** = config-level secrets only (Q1). The Module 4 input's "encryption utility for the password field" was disambiguated to mean connector-config secrets (API keys, auth tokens, etc.), NOT the per-row CSV `password`. Parent `FR-010` (CSV password = in-memory only) is unchanged; new parent `FR-023a` formalizes the at-rest encryption rule for config-level secrets across the whole harness (wizard persistence, detail-view rendering, export emission).
  2. **Connection lifecycle** = once per job (Q2). `connect()` at job start; same handle across all rows; `disconnect()` at job end. Mid-job session-expiry is the connector's internal concern.
- Auto-applied reconciliations:
  - **TypeScript-style method signatures** reframed as behavioral requirements; literal language binding is plan-level.
  - **Reference to "Standard Evaluation Contract (module 1)"** treated as a reference to `specs/006-evaluation-contract` (our numbering, not the user's "Module 1").
  - **"MockConnector as a reference implementation"** kept as a real shipped artifact (FR-020–FR-024), not just a doc example.
  - **`sendUtterance(handle, utterance, testId, password)`** keeps `password` as a parameter, consistent with parent FR-006 — the connector receives it for use against the chatbot's identity system; the framework neither inspects nor logs it.
- Cross-module impact: this spec **amends the parent harness spec (001)** in lock-step:
  - New parent `FR-023a` — config-level secret-encryption-at-rest with a machine-local key. Cited by `specs/004-job-detail-view` → `FR-005` (masked display) and `specs/005-results-export` → `FR-011` (masked in export) but those existing rules don't change; they're still about hiding from view, and now they sit on top of encrypted-at-rest persistence.
  - New parent `Clarifications` bullet documenting the Module 4-driven choice.
- The framework's secret encryption story is what makes connectors safe to ship beyond a single tester's laptop. It is additive defense-in-depth over the existing masking-at-render rules; it does not change any UI surface or any export surface.
- No `[NEEDS CLARIFICATION]` markers emitted; both genuine pre-spec ambiguities resolved before writing.
- **Re-validated 2026-05-28 (Round 2)** after `/speckit-clarify` session (2 Qs accepted, loop stopped early — remaining items are plan-level): `connectorId` is the **sole connector identity in v1**, no separate version field; version-coexistence handled by id-baked convention (`FR-009` updated); framework **serializes `sendUtterance` per `ConnectionHandle`** in v1 (new `FR-007a`), pinning parent's "max concurrent in-flight rows per job" tuning to 1 for v1. Cross-job parallelism unaffected. All 16 checklist items remain passing; no regressions; no new [NEEDS CLARIFICATION] markers introduced.
