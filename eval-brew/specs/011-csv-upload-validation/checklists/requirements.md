# Specification Quality Checklist: CSV Upload & Validation Service (Module 8)

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

- **Pre-spec decision: Q1 = "No — honor 010 Q2"** (third consecutive consistent vote — 010 Q2, 009 R1 Q1, and this round all agree). The Module 8 input's three credential-persistence directives (encrypt passwords on Utterance, retain raw CSV, reference file in-place) were explicitly NOT applied. Module 8 contains zero new persistence story for credentials; it only documents the in-memory handoff rule (`FR-015`) by which parsed passwords reach the orchestrator without ever touching disk.
- **Auto-applied: CSV column name standardization on `utteranceText`** in lock-step amendments to:
  - `001 FR-002` (parent): `utterance` → `utteranceText`
  - `006 FR-002` (contract): "`utterance` column" → "`utteranceText` column"
  - `009 FR-002` (data model): "CSV's `utterance` column" → "CSV's `utteranceText` column"
  
  The user used `utteranceText` in their Module 3 and Module 8 inputs; I had drifted to `utterance` in the earlier specs. Two repetitions of `utteranceText` from the user wins; specs realigned.
- **Auto-applied (precedent / spec discipline)**:
  - No `createdBy` on the Module 8 service itself — single-user. The Job's `createdBy` is set by the wizard at Step 1 (per `003 FR-004`), not at Step 2 upload time.
  - 1-based `rowIndex` per `009 R2 Q2` — Module 8's `FR-013` honors this.
  - UUID v4 / globally-unique `utteranceId` per `006 FR-002` and `009 FR-002`.
  - Atomic commit (Utterance rows + counter + filename together) per `009 FR-020`.
  - Reject non-draft uploads per `009 FR-005` snapshot immutability.
  - Cross-spec connector module references (`007`), evaluator (`008`), orchestrator (Module 10 = TBD) — forward references handled cleanly.
- **Notable design decisions baked in**:
  - **In-memory password store** (`FR-015`) is documented as a process-scoped, plan-level shape (Python dict vs. service object vs. DI binding — plan picks). The spec only requires: process-scoped, not on disk, not visible to non-harness processes, cleared on process exit, SHOULD clear on Job-terminal.
  - **Configurable max file size** (`FR-002`) — knob value plan-level (default suggested 50 MiB), but the configurability and the pre-read enforcement are spec-level.
  - **Per-error response array** (`FR-020`) — for tester-facing per-row errors on the wizard's Step 2. Each entry carries category + row + column + description.
  - **UTF-8 BOM silently stripped** (`FR-004`) — not a warning, since BOM is harmless and common.
  - **Trailing blank rows silently skipped** (`FR-011`) — warning, not error, since they're harmless and common in spreadsheet exports.
  - **Whitespace-trim on header names** (`FR-006`) — Excel exports often add whitespace; harmless to tolerate.
  - **Non-comma delimiters rejected** (`FR-005`) — v1 simplicity; plan-level enhancement could auto-detect.
  - **`[MASKED]` re-upload not detected** (Edge case) — if a tester re-uploads a previously-exported (masked) file, Module 8 doesn't notice; the connector surfaces auth failure at run time. Acknowledged limitation.
  - **`Job.sourceCSVFilename` = basename only** (`FR-017`) — not the full path; preserves the parent's "no file artifact retained" stance while still letting the detail-view metadata panel show "what file did this come from."
- **No parent-spec amendments beyond the column-name alignment** (which itself was a tightening, not a directional change). The pre-spec decision honored precedent; only naming consistency moved.
- No `[NEEDS CLARIFICATION]` markers emitted; the genuine pre-spec ambiguity was resolved before writing.
- **Re-validated 2026-05-29 (Round 2)** after `/speckit-clarify` session (2 Qs accepted, loop stopped — remaining items are plan-level): **Replace-on-upload** for re-uploads to draft Jobs (new `FR-018a`; atomic delete-then-apply pattern; matches `003 FR-019`); **per-row eviction** for in-memory password store with Job-terminal backstop + process-exit clear (`FR-015` rewritten with three-tier lifecycle); `FR-018` tightened to include the in-memory store in the atomicity scope; new `SC-011`/`SC-012`/`SC-013` verify replace-atomicity and per-row eviction. All 16 checklist items remain passing; no regressions; no new [NEEDS CLARIFICATION] markers introduced.
