# BL-005 — Dimension Declaration: Cap, Scale Bounds, and Registration-Time Validation

**Created:** 2026-08-08
**Status:** Specced
**Area:** Evaluator Registry / Orchestrator / Results UI / Export
**Stakeholders:** Engineers, QA Leads, Harness Admins

---

## Overview

Dimensions are currently registered as a plain ordered list of name strings with no
count limit, no uniqueness enforcement, and no score-range metadata. This allows
silent data-quality failures — an evaluator returning 40 dimensions renders the UI
unusable; a score of `7` lands in the "Score (0–1)" export column with no warning.

This spec closes those gaps by adding three constraints enforced at registration time
and one additional validation enforced at evaluation response time:

1. **Maximum 10 declared dimensions** (hard error, not warning)
2. **Unique dimension names** (hard error, not warning)
3. **Declared score scale** — a single min/max pair covering all dimensions —
   mandatory when at least one dimension is declared
4. **Response-time range validation** — scores outside the declared bounds are
   rejected with `errorStage = evaluator_result`

The evaluator response shape (`{parameter_name, score, reasoning}` per entry in
`evaluationScores`) is **not changed**. The harness reads the declared scale from
the registration record, not from the evaluator response.

---

## Design Decisions (Resolved)

| Decision | Choice | Rationale |
|---|---|---|
| Scale granularity | **Single min/max for all dimensions** | Per-dimension scale would require a structured form, a schema migration to a nested object model, and cross-dimension normalisation before aggregation — complexity not warranted given the uniform 0–1 convention in use |
| Dimension declaration style | **One per line in a textarea** (unchanged) | Existing UX is familiar; adding a hard cap and duplicate check is sufficient without restructuring to individual input rows |
| Scale mandatory when? | **When ≥ 1 dimension is declared** | Zero-dimension evaluators (pure-verdict) have no scores to range-check; forcing a scale on them is meaningless |
| Out-of-range score treatment | **Hard error — `errorStage = evaluator_result`** | A score outside the declared bounds signals an evaluator bug or a stale registration; surfacing it as a row failure is preferable to silently propagating a corrupted value into the export |
| String scores | **Bypass range validation** | The existing spec (FR-008a / spec 008 FR-005) permits `score` to be a `number or short string`; this allowance is preserved |
| Analytics normalisation | **Declared scale used for overall mean and histograms** | Makes the overall mean comparable across evaluator versions and makes histogram bucket positions absolute rather than distribution-relative |
| Evaluator response shape | **Unchanged** | No modification to spec 008, FR-003, or FR-008a |
| Migration | **Existing registrations get NULL scale; no forced default** | Avoids silently applying a wrong default; existing registrations continue to work without scale validation until an admin edits and saves them |
| Scale polarity | **Higher score = better performance (v1 constraint)** | Allows a single normalisation formula (min → 0.0, max → 1.0); evaluators where lower is better must normalise internally — out of scope for this version |

---

## Current State

| Concern | Current behaviour |
|---|---|
| Max dimensions | Unlimited — no cap enforced |
| Dimension uniqueness | Non-blocking warning only |
| Score type | `number` or `string` (booleans excluded); no range check |
| Scale declaration | No field on the registration form or model |
| Out-of-range scores | Accepted, persisted, displayed as-is |
| Overall mean score | Raw float average; meaningless across evaluators with different scales |
| Analytics histograms | Min-max normalise the run's own distribution |
| UI/export label | `Score (0–1)` — aspirational documentation, not a constraint |

**Key code locations**

| Concern | File | Lines |
|---|---|---|
| Registration form | `src/harness/ui/evaluator_registry/templates/evaluator_registry/form.html` | 163–169 |
| Dimension parsing | `src/harness/evaluator_registry/forms.py` | 22–40 |
| Score validation | `src/harness/evaluator/validation.py` | 63–75 |
| Score consumption | `src/harness/ui/detail/view.py` | 383 |
| Analytics — normalise | `src/harness/ui/detail/analytics.py` | 87–93 |
| Analytics — overall mean | `src/harness/ui/detail/analytics.py` | 285 |
| ORM model | `src/harness/persistence/models/evaluator_registration.py` | `declared_scoring_dimensions` JSON column |

---

## User Scenarios

### Scenario A — Admin registers a new evaluator with 4 dimensions and scale 0–1

The admin fills in 4 dimension names (one per line), enters `0` in Score minimum and
`1` in Score maximum, and saves. The form shows "4 / 10 dimensions." The registration
is accepted. Future jobs using this evaluator have the scale `[0.0, 1.0]` snapshotted
alongside the other evaluator config.

### Scenario B — Admin attempts to register 11 dimensions

The admin enters 11 dimension names and submits. The form rejects the save with a
blocking error: *"Maximum 10 dimensions allowed (11 declared)."*
The registration is not saved.

### Scenario C — Admin enters duplicate dimension names

The admin enters `accuracy`, `fluency`, `accuracy` (case-sensitive duplicate). The
form rejects with: *"Dimension names must be unique. Duplicate: 'accuracy'."*

### Scenario D — Admin declares ≥ 1 dimension but leaves scale blank

The admin enters dimension names but leaves Score minimum and/or Score maximum empty.
The form rejects with: *"Score minimum and maximum are required when dimensions are
declared."*

### Scenario E — Admin enters an invalid scale (min ≥ max)

Admin enters Score minimum = `1.0` and Score maximum = `0.5`. The form rejects with:
*"Score minimum must be strictly less than Score maximum."*

### Scenario F — Evaluator returns an out-of-range score at runtime

A job is running. The evaluator returns `"score": 1.4` for dimension `accuracy` and
the declared scale is `[0.0, 1.0]`. The harness rejects the row:
`errorStage = evaluator_result`, detail: *"score 1.4 for dimension 'accuracy' is
outside the declared scale [0.0, 1.0]"*. The remaining rows in the job continue
processing normally.

### Scenario G — Admin edits an existing (pre-migration) registration

The admin opens an existing registration that has dimensions but no declared scale
(created before this feature). The form displays the existing dimensions and the
scale fields rendered as empty/blank. On save, the scale fields become required and
the admin must supply them before the save is accepted.

---

## Functional Requirements

### Registration — Dimension Constraints

**FR-001** The registration form and POST handler MUST reject saves where the number
of declared dimensions (after parsing: trim whitespace, drop blank lines) exceeds 10.
The error MUST state the count and the limit:
*"Maximum 10 dimensions allowed (N declared)."*
This is a blocking validation error — the registration is not saved.

**FR-002** The registration form and POST handler MUST reject saves where any two
parsed dimension names are equal (case-sensitive string comparison after trimming).
The error MUST name all duplicate names in a single message:
*"Dimension names must be unique. Duplicate(s): {comma-separated list of duplicate names}."*
For example, with duplicates `accuracy` and `fluency`:
*"Dimension names must be unique. Duplicate(s): 'accuracy', 'fluency'."*
This upgrades the existing non-blocking warning to a blocking error.

**FR-003** The registration form MUST display a live dimension count indicator
adjacent to the dimensions textarea that updates as the user types.
The indicator format is: *"N / 10 dimensions"*.
At 10 dimensions the indicator MUST visually signal the limit is reached
(e.g., text colour change, bold). This is a client-side UI-only feature;
it does not replace server-side enforcement in FR-001.

### Registration — Scale Declaration

**FR-004** The evaluator registration form MUST include two new numeric input fields:
**Score minimum** and **Score maximum**. Both accept integer or decimal values
(e.g., `0`, `0.0`, `1`, `1.0`, `10`).

**FR-005** Score minimum and Score maximum are **required when at least one dimension
is declared** and **optional when zero dimensions are declared**.
If one or both scale fields are blank and at least one dimension is declared, the save
MUST be rejected with:
*"Score minimum and maximum are required when dimensions are declared."*

**FR-006** The value of Score minimum MUST be strictly less than the value of Score
maximum. Saves where `scale_min >= scale_max` MUST be rejected with:
*"Score minimum must be strictly less than Score maximum."*
This rule applies regardless of whether the values are integers or decimals.

**FR-007** Declared scale values MUST be numeric. Non-numeric input (e.g., letters,
symbols) in either field MUST be rejected at two layers:
- At the form level with a field-level validation error (HTML5 `type="number"` or
  equivalent client-side guard).
- In the POST handler: the handler MUST attempt `float(value)` for each scale field
  and return a 400 error with a field-level message on `ValueError`, before applying
  FR-005 and FR-006 checks. This guards against direct HTTP POST requests that bypass
  the browser form (consistent with the server-side numeric guard used for
  `timeout_seconds` in the evaluator registration handler).

### Data Model

**FR-008** The `EvaluatorRegistration` model MUST gain two new columns:
`score_scale_min` (`Float`, nullable) and `score_scale_max` (`Float`, nullable).
Both are `NULL` for registrations created before this feature (see Migration).
Both are `NULL` for zero-dimension registrations where scale was not supplied.
When scale is supplied (FR-005 satisfied), both are stored as the user-entered
float values.

**FR-009** The evaluator configuration snapshot captured at job creation
(per spec 008 FR-012) MUST include the `score_scale_min` and `score_scale_max`
values as part of the snapshot. This ensures that edits to a registration's scale
after job creation do not retroactively affect running or historical jobs.
The snapshot key names are `score_scale_min` and `score_scale_max`.

### Response-Time Validation

**FR-010** When the orchestrator processes an `EvaluationResult`, if the evaluator's
job-time snapshot contains a non-null `score_scale_min` and `score_scale_max`, the
harness MUST validate each entry in `evaluationScores` whose `score` field is a
numeric type (`int` or `float`; booleans excluded per existing rules) against the
declared range `[score_scale_min, score_scale_max]` (inclusive on both ends).

**FR-011** A numeric score that falls outside `[score_scale_min, score_scale_max]`
MUST cause the row to be recorded with `errorStage = evaluator_result`.
The error detail MUST name the offending dimension and the out-of-range value:
*"score {value} for dimension '{name}' is outside the declared scale
[{scale_min}, {scale_max}]"*.
If multiple dimensions have out-of-range scores in the same response, all violations
MUST be listed in the error detail before the row is failed.
Per-row failure isolation is preserved — subsequent rows continue processing (parent
spec FR-016).

**FR-012** `score` entries whose value is a `string` type MUST bypass range
validation. The existing allowance for string scores (spec 008 FR-005,
parent FR-008a) is preserved unchanged.

**FR-013** `score` entries whose value is JSON `null` or whose key is entirely absent
from the entry MUST bypass range validation. A score of `0` (integer or float zero)
is a valid numeric value and MUST be range-validated per FR-010 — zero MUST NOT be
treated as absent or skipped. This bypass applies only to the orchestrator's
response-time validation (in `harness/evaluator/validation.py`); view-layer display
handling of null scores is a separate concern unchanged by this spec.

**FR-014** When the evaluator snapshot has `score_scale_min = None` or
`score_scale_max = None` (legacy registration without declared scale), range
validation is skipped entirely for that job. The row is not failed on account of
score range; existing behaviour is preserved.

### Analytics

**FR-015** When a job's evaluator snapshot has a declared scale (both
`score_scale_min` and `score_scale_max` are non-null), the `overall_mean_score`
reported in the analytics dashboard MUST be computed on linearly normalised values:

```
normalised(score) = (score − scale_min) / (scale_max − scale_min)
```

Only numeric scores (`int` or `float`) are included in this calculation. String
scores (FR-012) and null/absent scores (FR-013) are excluded — they do not
contribute to the mean and do not affect the denominator. If all scores for a job
are string or null, `overall_mean_score` is `None` and displayed as `—`.

The overall mean is then the arithmetic mean of these normalised values.
The result for included scores is always in `[0.0, 1.0]`.

**Assumption — higher score = better:** This normalisation formula maps `scale_min`
to `0.0` and `scale_max` to `1.0`, treating the maximum as the best possible
outcome. Evaluators where a lower score indicates better performance (e.g., an
error-count metric on scale `[0, 10]`) are not supported in this version — their
normalised overall mean will invert the quality signal. Such evaluators must
normalise their scores before emission so that higher = better within the declared
scale. Support for explicit lower-is-better polarity is deferred to a future
iteration.

**Note — divergence with per-parameter stat tiles (FR-021):** For jobs where
`scale_min = 0` and `scale_max = 1`, the normalised `overall_mean_score` and the
raw "Mean" value in the per-parameter stat tiles are numerically identical. For any
other declared scale (e.g., `[0, 10]`), the two will differ: the overall mean is
expressed in `[0, 1]` while the per-parameter Mean tile shows the raw value in the
declared range (e.g., `0.73` vs `7.3`). This is intentional — the overall mean is
a canonical cross-dimension composite; the per-parameter tiles preserve the
evaluator's native scale for direct comparison with the evaluator's own output.

**FR-016** When a job has a declared scale, the analytics histogram for each
parameter MUST use the declared `[scale_min, scale_max]` as the normalisation
bounds instead of the run's own distribution min and max.
This makes bucket positions absolute: a score at 70% of the declared range always
appears at the 70% mark on the histogram, regardless of how other scores in the
run are distributed.

**FR-017** When a job has no declared scale (legacy), analytics behaviour is
unchanged: `overall_mean_score` is the raw arithmetic mean and histograms
min-max normalise against the run's own distribution.

### Display

**FR-018** The evaluator registration detail/view page MUST display the declared
scale when set (e.g., *"Score scale: 0.0 – 1.0"*) and *"Scale: not declared"* for
legacy registrations where scale is null.

**FR-019** The data dictionary sheet of the flat XLSX export and the companion
`_data_dictionary.csv` (BL-002/BL-003) MUST include the declared scale in the
row that describes the score columns. When scale is declared the description
reads: *"Numeric score on the declared scale [{scale_min} (minimum) — {scale_max}
(maximum)]. Values are reported as received from the evaluator (not normalised).
This spec assumes higher score = better performance."*
When scale is not declared it reads: *"Numeric score (scale undeclared;
values reported as received from the evaluator)"*.

**FR-020** Score cell values in all export formats (flat CSV, flat XLSX,
PBI-compatible CSV, PBI-compatible XLSX, JSON) MUST contain the raw numeric value
as received from the evaluator — not a normalised value. The declared scale is
contextual metadata (shown in headers and data dictionary) not a transform applied
to the persisted data.

**FR-021** The per-parameter stat tiles in the analytics dashboard (Mean, Median,
Min, Max, Range, σ) MUST display raw score values as received from the evaluator.
No normalisation is applied to these tiles.

**Note:** The declared scale is visible on the evaluator registration detail page
(FR-018) but is not surfaced directly on the analytics dashboard in this version.
Users who need scale context while reviewing analytics must navigate to the evaluator
registry to find it. Inline display of the declared scale on the analytics page is
deferred to a future iteration.

**FR-022** Wherever a score column label currently reads `Score (0–1)` — in flat
CSV/XLSX column headers, PBI-compatible CSV/XLSX column headers, and the detail
view results table score column — the label MUST be rendered dynamically from the
job's evaluator snapshot:

- When the snapshot contains a declared scale: `Score ({scale_min}–{scale_max})`
  (e.g., `Score (0.0–1.0)`, `Score (0–10)`)
- When the snapshot has no declared scale (legacy job): the label is unchanged —
  `Score (0–1)` is retained for backward compatibility

The same dynamic rule applies to per-dimension column headers in the flat format:
`{name}: Score ({scale_min}–{scale_max})` replaces the current hardcoded
`{name}: Score (0–1)`.

The scale values are read from the job snapshot (FR-009), not from the live
registry, so historical jobs render with the scale that was declared at the time
the job was created.

---

## Data Model Changes

### `EvaluatorRegistration` (existing table)

Two columns added:

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `score_scale_min` | `Float` | Yes | `NULL` | Lower bound (inclusive) of the declared score range |
| `score_scale_max` | `Float` | Yes | `NULL` | Upper bound (inclusive) of the declared score range |

No other columns on this model change.

### Evaluator config snapshot (stored in `Job` or equivalent)

The snapshot dict gains two keys alongside existing evaluator fields:

```python
{
    # existing keys unchanged
    "evaluation_agent_id": "...",
    "display_name": "...",
    "endpoint_url": "...",
    "auth_descriptor": {...},
    "timeout_seconds": 60,
    "declared_scoring_dimensions": [...],
    # new keys
    "score_scale_min": 0.0,   # or None if not declared
    "score_scale_max": 1.0,   # or None if not declared
}
```

---

## Validation Rules Summary

| Rule | Location | Error type |
|---|---|---|
| Dimension count > 10 | Form + POST handler | Blocking error |
| Duplicate dimension name | Form + POST handler | Blocking error |
| Scale required when ≥ 1 dimension declared | Form + POST handler | Blocking error |
| Scale fields non-numeric | Form (client-side) + POST handler | Field-level error |
| `scale_min >= scale_max` | Form + POST handler | Blocking error |
| Numeric score outside `[scale_min, scale_max]` | Orchestrator, response time | `errorStage = evaluator_result` |
| String score (numeric range check not applicable) | Orchestrator | Bypassed (no error) |
| Missing / null score out-of-range | Orchestrator | Bypassed (no error) |
| Legacy registration (null scale) at response time | Orchestrator | Bypassed (no error) |

---

## Migration

A database migration MUST add `score_scale_min` and `score_scale_max` as nullable
`Float` columns to the `evaluator_registration` table. Both default to `NULL`.

No data backfill is applied. Existing registrations remain with `NULL` scale values
and continue to operate under the legacy (no-range-validation) path (FR-014).

When an admin opens an existing registration for editing, the scale fields are
rendered as empty. On save, the new validation rules (FR-005, FR-006) apply — the
admin MUST supply a valid scale before the update is accepted.

Admins are not force-prompted to update existing registrations unless they
choose to edit them.

---

## Relationship to Other Backlog Items

- **BL-004 (Verdict aggregation transparency):** BL-004 addresses the rollup rule
  for verdicts and evaluator threshold declarations. BL-005 addresses the numeric
  score range only. The two are orthogonal — the score scale (BL-005) bounds what
  value range is valid; the threshold (BL-004) determines which part of that range
  maps to pass/warn/fail. BL-005 can ship independently.
- **BL-003 (Stakeholder-friendly headers / data dictionary):** The data dictionary
  entry *"Score (0–1): 0.0 worst — 1.0 best"* becomes accurate and verifiable
  once BL-005 is live. FR-019 amends the data dictionary description that BL-003 introduced — the score
  column description is updated to reference the declared scale and note that values
  are raw (not normalised).
- **BL-002 (Flat CSV/XLSX):** Score cell values in the flat export remain raw
  (FR-020). The data dictionary reflects the declared scale (FR-019). Column
  headers become dynamic (FR-022): `{name}: Score ({min}–{max})` replaces the
  hardcoded `{name}: Score (0–1)`. Both builders (`results_flat_csv_builder`,
  `results_flat_xlsx_builder`) read scale from `job.evaluation_agent_config`.

---

## Resolved Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Score columns in exports: raw or normalised? | **Raw** — cell values are faithful to what the evaluator sent (FR-020) |
| 2 | Per-parameter stat tiles: raw or normalised? | **Raw** — Mean/Median/Min/Max/Range/σ tiles show raw values; declared scale visible on registration page provides context (FR-021) |
| 3 | Score column label: static or dynamic? | **Dynamic** — rendered as `Score ({min}–{max})` from the job snapshot; legacy jobs without a declared scale keep the existing `Score (0–1)` label (FR-022) |

---

## Acceptance Criteria

- [ ] Saving a registration with > 10 dimension names is rejected with a clear error
      stating the count and the limit.
- [ ] Saving a registration with duplicate dimension names (case-sensitive) is
      rejected; all duplicates are named in the error.
- [ ] The registration form shows a live "N / 10 dimensions" count that updates
      as the user types without requiring a page submission.
- [ ] Saving a registration with ≥ 1 dimension but no scale min/max is rejected.
- [ ] Saving a registration with zero dimensions and no scale min/max is accepted.
- [ ] Saving a registration where `scale_min >= scale_max` is rejected.
- [ ] `EvaluatorRegistration` model has `score_scale_min` and `score_scale_max`
      nullable float columns after migration.
- [ ] The evaluator config snapshot stored at job creation includes
      `score_scale_min` and `score_scale_max`.
- [ ] At evaluation response time, a numeric score outside `[scale_min, scale_max]`
      causes `errorStage = evaluator_result` with an error detail naming the dimension
      and value; the job continues processing other rows.
- [ ] A string score value in `evaluationScores` does not trigger range validation.
- [ ] A job with a declared scale whose evaluator returned only string scores
      completes analytics without error; string scores are excluded from the
      normalised `overall_mean_score`, which is reported as `None` / `—`.
- [ ] A job running against a legacy registration (null scale) does not produce
      range-validation failures.
- [ ] `overall_mean_score` in the analytics dashboard is computed on
      [0, 1]-normalised values when scale is declared.
- [ ] Analytics histograms use declared scale bounds as the normalisation range
      when scale is declared.
- [ ] The evaluator registration detail page shows the declared scale or
      "Scale: not declared" for legacy registrations.
- [ ] The flat XLSX Data Dictionary sheet and companion CSV reflect the declared
      scale in the score column description (FR-019).
- [ ] Score cell values in flat CSV, flat XLSX, PBI CSV, PBI XLSX, and JSON
      exports are the raw values received from the evaluator — not normalised (FR-020).
- [ ] Per-parameter stat tiles (Mean, Median, Min, Max, Range, σ) show raw score
      values; no normalisation is applied (FR-021).
- [ ] Flat CSV/XLSX column headers render as `{name}: Score ({min}–{max})` when
      the job snapshot has a declared scale (FR-022).
- [ ] PBI-compatible CSV/XLSX score column header renders as `Score ({min}–{max})`
      when the job snapshot has a declared scale (FR-022).
- [ ] The detail view results table score column header renders dynamically from
      the job snapshot (FR-022).
- [ ] Jobs with no declared scale (legacy) retain the existing `Score (0–1)` label
      unchanged across all surfaces (FR-022 backward compatibility).
- [ ] Editing an existing (pre-migration) registration with dimensions requires
      supplying a valid scale before the update is accepted.
- [ ] Editing an existing pre-migration registration with zero dimensions and no
      scale values is accepted without requiring scale values (FR-005 zero-dimension
      exemption).
- [ ] All existing tests pass; new tests cover each acceptance criterion above.
