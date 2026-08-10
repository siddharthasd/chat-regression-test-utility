# BL-004 — Verdict Aggregation Transparency: Publish Threshold and Rollup Rules

**Created:** 2026-08-08
**Status:** Backlog
**Area:** Results UI / Results Export / Evaluator Framework
**Stakeholders:** QA Leads, HR SMEs, Compliance, Business Analysts, Engineers

---

## Problem Statement

The overall verdict (`pass` / `warn` / `fail`) is emitted at the row level and
surfaced throughout the harness — in the job detail view, the analytics dashboard,
and all CSV/XLSX exports. Yet the logic that produces this verdict is invisible to
anyone reading the results:

**Layer 1 — Per-dimension threshold rules (evaluator-owned):**
Each evaluator scores every dimension on a numeric scale (0.0–1.0) and maps that
score to a verdict band. The mapping — e.g., "relevance ≥ 0.8 → pass, 0.6–0.8 →
warn, < 0.6 → fail" — is internal to the evaluator service and is never communicated
to the harness or stored alongside the result. A stakeholder seeing a relevance score
of `0.71` with a `warn` verdict has no way to know whether the threshold is `0.75` or
`0.80`, whether `0.71` is close to a pass or close to a fail, or what the evaluator
considers an acceptable baseline.

**Layer 2 — Row-level rollup rule (harness-owned):**
The harness combines N dimension-level verdicts into one overall verdict using a
worst-case rule: if any dimension is `fail` the row is `fail`; if any is `warn` and
none is `fail` the row is `warn`; only if all are `pass` does the row pass. This rule
exists in code (and is referenced in the analytics tooltip copy at
`src/harness/ui/detail/routes.py`) but is never displayed to the user — not in the
UI, not in the export data dictionary, not in any tooltip on the verdict cell.

Together these two gaps make it impossible to:
- Diagnose borderline cases ("why is this row a fail when the score is 0.62?")
- Explain verdicts to stakeholders in a governance or audit context
- Compare results across jobs where different evaluator versions may have applied
  different thresholds

---

## Current Behaviour

| Surface | What is shown | What is missing |
|---|---|---|
| Job detail — Results table | Score + verdict per dimension; overall verdict per row | Threshold bands; rollup rule |
| Analytics dashboard — Overview tiles | Pass/warn/fail counts; distribution bars | Threshold context |
| CSV/XLSX flat export (BL-002) | Score + result columns | No threshold columns; rollup rule absent from data dictionary |
| Data dictionary (BL-003) | Qualitative definitions of pass/warn/fail | No quantitative thresholds; no rollup formula |
| Evaluator registration (module 014) | Endpoint + auth + declared dimensions | No threshold declaration fields |

The BL-003 data dictionary defines verdicts qualitatively ("score meets or exceeds
the configured threshold") but "configured threshold" refers to an opaque value that
is neither stored in the harness nor visible anywhere.

---

## Desired Behaviour

### 1. Surface the harness rollup rule

The worst-case rollup rule should be stated explicitly wherever the overall verdict
appears:

- **Detail view sidebar / tooltip**: "Overall Result: worst-case across all
  dimensions. If any dimension is fail → fail; if any is warn → warn; otherwise pass."
- **Data dictionary (BL-003 export)**: Add a row for "Overall Result" that states the
  rollup rule in plain language.
- **Analytics dashboard tile**: Sub-caption or info icon explaining the rollup.

This is a low-effort, zero-protocol-change fix that closes the harness-owned gap
immediately.

### 2. Allow evaluators to declare threshold bands at registration

Extend the evaluator registration (module 014) with an optional
`scoring_thresholds` metadata field — a per-dimension declaration of the form:

```json
"scoring_thresholds": {
  "relevance":    { "pass": 0.80, "warn": 0.60 },
  "grounding":    { "pass": 0.75, "warn": 0.50 },
  "completeness": { "pass": 0.70, "warn": 0.50 },
  "tone":         { "pass": 0.80, "warn": 0.65 }
}
```

Semantics: score ≥ `pass` threshold → pass; score ≥ `warn` threshold → warn; score
< `warn` threshold → fail. The field is optional; if absent the harness shows
"thresholds not declared by this evaluator."

### 3. Show thresholds in the result detail view

When threshold metadata is available for the evaluator that scored a row, the detail
view should render it alongside each dimension's score — e.g., as a small threshold
indicator or progress bar showing where the score falls within the pass/warn/fail
bands. This gives engineers and stakeholders immediate context for borderline scores.

### 4. Include thresholds in exports

When threshold metadata is available, include it in:
- The XLSX Data Dictionary sheet (per-dimension threshold rows)
- The job-level metadata block of the JSON export
- Optionally, per-dimension threshold columns in the flat CSV (pass_threshold,
  warn_threshold) for pivot-friendly analysis

---

## Impact

- **Without this:** A `warn` at 0.71 is indistinguishable from a `warn` at 0.79 to a
  stakeholder. Governance and audit reviews require engineering involvement to explain
  every non-pass result. Teams frequently misread borderline scores as clearly failing
  or safely passing when they are neither.
- **With this:** Stakeholders can self-serve explanation of any verdict. Engineers can
  spot threshold drift across evaluator versions. The data dictionary becomes a
  complete audit record of the decision logic that produced each result file.

---

## Acceptance Criteria

- [ ] The worst-case rollup rule is stated in the detail view wherever the overall
      verdict column appears (tooltip or sub-label).
- [ ] The data dictionary (BL-003 export) includes an "Overall Result" entry that
      states the rollup rule explicitly.
- [ ] The evaluator registration form (module 014) accepts an optional
      `scoring_thresholds` JSON field per declared dimension.
- [ ] The harness stores declared thresholds alongside the evaluator registration
      and associates them with results produced by that evaluator version.
- [ ] When thresholds are declared, the detail view renders a per-dimension
      threshold indicator (score vs threshold band) on the results table.
- [ ] When thresholds are absent, the UI shows "Thresholds not declared by evaluator"
      rather than a blank or missing element.
- [ ] Thresholds are included in the XLSX Data Dictionary sheet and JSON export
      metadata when present.
- [ ] All existing tests pass; new tests cover threshold storage, UI rendering,
      and export inclusion.

---

## Relationship to Other Backlog Items

- **BL-003 (Stakeholder-friendly headers / data dictionary):** The data dictionary
  introduced by BL-003 is the natural home for the rollup rule and threshold
  declarations. BL-004 extends BL-003's dictionary rather than replacing it. Ideally
  BL-004's data dictionary additions ship alongside or shortly after BL-003.
- **BL-002 (Flat CSV/XLSX download):** If BL-004 adds per-dimension threshold columns
  to the flat export, the column-naming conventions from BL-002/BL-003 should be
  followed (human-friendly names, same `_HEADER_MAP` pattern).
- **Module 014 (Evaluator Registry):** The `scoring_thresholds` field is a schema
  addition to the evaluator registration. Any migration for 014 must account for
  existing registrations that will have no threshold data.

---

## Open Questions

1. **Threshold ownership:** Thresholds are an evaluator concern; should the harness
   store them at all, or should it fetch them on-demand from the evaluator's
   `/metadata` endpoint each time? Storing at registration is simpler but requires the
   harness to track threshold versions if the evaluator re-registers with new values.
2. **Threshold versioning:** If an evaluator changes its thresholds between two job
   runs, historical results should be annotated with the threshold that applied at
   the time of evaluation. How does the harness associate "threshold snapshot at job
   time" with the result?
3. **Non-numeric scores:** Some evaluators may use non-numeric scores (e.g., labels).
   The threshold declaration schema above assumes numeric 0–1. Should the spec allow
   label-based thresholds (e.g., `{"pass": ["correct"], "warn": ["partial"]}`) or
   restrict to numeric?
4. **Rollup rule extensibility:** The harness currently uses worst-case. Should future
   evaluators be able to declare an alternative rollup (e.g., weighted average of
   dimension verdicts)? Or is worst-case the permanent harness-level invariant?
5. **Scope of change to module 014:** Adding `scoring_thresholds` to the registration
   form requires a database migration and a UI change. Is that in scope for BL-004
   or should the data-dictionary fix (§1) ship first as a quick win?

---

## Candidate Solutions

- **Option A — Documentation only (quick win):** Add the rollup rule to the data
  dictionary and the detail-view tooltip with no schema or protocol changes. Closes
  the harness-owned gap immediately. Threshold rules remain opaque (evaluator
  responsibility to document externally). Low effort, partial fix.
- **Option B — Evaluator metadata endpoint:** Define a standard `/metadata` endpoint
  on the evaluator wire protocol that returns threshold declarations. The harness
  fetches this at job start and stores a snapshot. No schema change to the
  registration form; thresholds are always fresh from the evaluator.
- **Option C — Registration-time declaration (preferred):** Add the optional
  `scoring_thresholds` field to the evaluator registration. Stored as a JSON snapshot;
  versioned by evaluator registration update. The harness displays and exports it.
  Requires a migration and a 014 UI change but makes thresholds a first-class,
  auditable, stored artefact.
- **Option D — Per-result annotation:** The evaluator wire protocol is extended so
  each EvaluationResult carries the thresholds that applied to produce it. No
  registration-form change; thresholds travel with results. Higher per-result payload
  size; breaks existing evaluator implementations without a protocol version bump.
