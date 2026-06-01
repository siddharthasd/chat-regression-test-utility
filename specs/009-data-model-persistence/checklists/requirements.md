# Specification Quality Checklist: Data Model & Persistence Layer (Module 2)

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
  1. **Password persistence** = honor parent `FR-010` (Q1). The Module 2 input's `encryptedPassword` field on Utterance is dropped; the raw CSV file is NOT retained on disk. Module 4's encryption utility stays scoped to config-level secrets only. Parent `FR-010` / `FR-010a` unchanged; `004 FR-006` (reconstructed source-CSV download) still applies; no parent-spec amendments needed.
  2. **Status enum** = parent's canonical 7-value lowercase enum (Q2). The Module 2 input's `Configured` and `CompletedWithErrors` are dropped — `Configured` isn't a defined state and `CompletedWithErrors` is a Module 13 UI label derived from `status == completed && failed_count > 0`. No parent-spec amendments needed.
- Auto-applied (precedent / spec discipline):
  - **No `createdBy`** on Job — single-user precedent.
  - **TesterFeedback entity added** (`FR-004`) — the user's input missed it, but parent's `Tester Feedback` entity + Module 13's `FR-010` make it real. At-most-one per Utterance; cleared = deleted row.
  - **`harnessAnnotations` column on ExecutionResult** (`FR-003`) — introduced in Module 7 R2 (`008 FR-005a`) for the soft-warning location. Sibling of `evaluationResult`, distinct from the agent's `metadata`.
  - **SQLAlchemy / SQLite / Alembic** — implementation choices, reframed as plan-level. The spec describes data shape, immutability invariants, and persistence behavior, not the library binding.
  - **`harnessVersion` on Job** kept — useful forensic stamp.
  - **DB file location configurable, default `~/.harness/data.db`** — `FR-017`, `FR-018`, `SC-011`.
- The split between **immutable snapshot fields** (`FR-005`, `FR-006`) and **mutable runtime-state fields** (`FR-007`) is the operational form of parent `FR-023`. The data layer is the enforcement boundary for "snapshots don't change."
- **`ExecutionResult` is the persistence form of both** the parent's `Connector Invocation` entity and the parent's `Evaluation Result` entity. It carries `rawChatbotResponse` (connector), `normalizedContract` (connector), `evaluationResult` (evaluator), and `harnessAnnotations` (harness). The split between connector-side and evaluator-side data within ExecutionResult is by column, not by separate tables.
- **`evaluationVerdict` is denormalized** from `evaluationResult.verdict` for query/filter performance — Module 13's verdict filter (`004 FR-012`) and the dashboard's filter (`002`) read it directly. The data layer guarantees the denormalization stays in sync at write time.
- **`testId` is denormalized** onto ExecutionResult — same rationale. Module 13's `testId` filter benefits.
- **Cascading deletion** is rigorously specified (`FR-010`, `FR-012`); the bulk-clear from the dashboard (`002 FR-010c`) maps to `FR-012`'s atomic enumerate-then-delete entry-point. Crucially, jobs that transition into `failed` / `cancelled` AFTER the bulk op starts MUST NOT be silently swept in.
- **Schema versioning + migration** (`FR-013`–`FR-016`) is in scope from v1 even though v1 ships one schema — without the mechanism in place at v1, v2's schema change has no migration path.
- **No `password` byte anywhere in the database file** is verifiable end-to-end (`SC-004`) via a known-distinctive value grep.
- No `[NEEDS CLARIFICATION]` markers emitted; both genuine pre-spec ambiguities resolved before writing.
- No parent-spec amendments needed this round. Both pre-spec choices (Q1, Q2) were "honor existing precedent" — so the only effect on the parent and other specs is that this Module 2 spec now formally pins the data-layer enforcement of rules already documented elsewhere.
- **Re-validated 2026-05-29 (Round 2)** after `/speckit-clarify` session (2 Qs accepted, loop stopped — remaining items are plan-level): cancelled-but-never-processed rows get **ExecutionResult stubs** at the `cancelling → cancelled` transition (new `FR-003a`); ExecutionResult becomes the single source of truth for per-row terminal state; `processedCount` and `failedCount` definitions on Job are pinned precisely (`FR-001` updated to exclude cancelled from both counts; `FR-003` `errorStatus` value semantics tightened). **`rowIndex` pinned to 1-based** at the data-layer boundary (`FR-002` updated; spec invariant `rowIndex >= 1` documented). All 16 checklist items remain passing; no regressions.
- **Re-validated 2026-05-29 (Round 4 — user-feedback removed)** after the cross-spec consistency pass: `TesterFeedback` entity dropped entirely (`FR-004` is now a "removed in v1" placeholder); `FR-007` immutability list no longer mentions TesterFeedback; `FR-010` cascade rule no longer mentions TesterFeedback; `FR-021` no longer enforces `feedbackId` uniqueness; entity list trimmed; `SC-001` / `SC-006` re-worded to drop the per-job feedback row count; `Cascade delete` description trimmed. The data layer's persisted entity set in v1 is three entities: Job, Utterance, ExecutionResult. All 16 checklist items remain passing.
