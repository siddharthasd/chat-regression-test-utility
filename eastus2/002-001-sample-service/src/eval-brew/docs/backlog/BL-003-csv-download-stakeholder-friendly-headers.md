# BL-003 — CSV Download: Stakeholder-Friendly Column Headers and Data Dictionary

**Created:** 2026-08-07
**Status:** Backlog
**Area:** Results Export / CSV Download
**Stakeholders:** HR SMEs, QA Reviewers, Business Analysts, Compliance

---

## Problem Statement

The current CSV export uses internal engineering field names as column headers:
`utteranceText`, `utteranceIntent`, `overallVerdict`, `parameterName`,
`evaluationTimestamp`, etc. These labels are meaningful to developers who wrote the
evaluation contract, but are opaque to HR SMEs, QA reviewers, and business stakeholders
who receive the file for sign-off or gap analysis.

Compounding the issue, there is no data dictionary anywhere in the export to explain
what values mean (e.g., what `warn` means operationally, what range scores occupy,
whether `fail` means total failure or partial failure).

Without readable headers and documented semantics, stakeholders either:
- Mis-interpret columns (e.g., reading `parameterName` as a technical parameter, not a
  scoring dimension).
- Route the file back to engineering for "translation" before they can review it.
- Produce commentary on the wrong column, causing rework.

---

## Current Column Headers (Engineering Labels)

| Engineering label | What it actually means |
|---|---|
| `utteranceId` | Internal UUID assigned to the test case |
| `utteranceText` | The user question / chatbot input |
| `utteranceIntent` | The intent category assigned to this query |
| `testId` | The reference ID from the original uploaded CSV |
| `parameterName` | The name of the scoring dimension (e.g., accuracy) |
| `score` | Numeric score for this dimension (0.0–1.0) |
| `overallVerdict` | Pass/fail/warn outcome for this dimension |
| `evaluationTimestamp` | When the evaluation ran |
| `evaluationAgentId` | Which evaluator scored this row |
| `chatbotResponse` | The chatbot's reply text |

---

## Desired Behaviour

### 1. Renamed column headers in the exported file

| Engineering label | Proposed human label |
|---|---|
| `utteranceId` | `Row ID` |
| `utteranceText` | `User Question` |
| `utteranceIntent` | `Intent Category` |
| `testId` | `Test Case Reference` |
| `parameterName` | `Dimension` |
| `score` | `Score (0–1)` |
| `overallVerdict` | `Result` |
| `evaluationTimestamp` | `Evaluated At` |
| `evaluationAgentId` | `Evaluated By` |
| `chatbotResponse` | `Chatbot Answer` |

> The mapping is the canonical source of truth for the harness and should be maintained
> in a single config file (not scattered across export functions).

### 2. Data dictionary tab / companion file

A second sheet (if Excel) or a companion `_data_dictionary.csv` (if ZIP) that defines
every column:

| Column name | Description | Type | Allowed values |
|---|---|---|---|
| `User Question` | The exact message sent to the chatbot | Text | Any UTF-8 string |
| `Intent Category` | Thematic classification of the question | Text | Defined by the evaluator |
| `Dimension` | The quality aspect being scored | Text | e.g., accuracy, relevance, grounding, completeness |
| `Score (0–1)` | Numeric quality score for this dimension | Decimal | 0.0 (worst) to 1.0 (best) |
| `Result` | Qualitative verdict for this dimension | Text | `pass`, `warn`, `fail` |
| `Overall Result` | Worst-case verdict across all dimensions for this query | Text | `pass`, `warn`, `fail` |

Definitions for verdict values:

| Value | Meaning |
|---|---|
| `pass` | Score meets or exceeds the configured threshold for this dimension |
| `warn` | Score is below threshold but above the minimum acceptable floor — review recommended |
| `fail` | Score is below the minimum acceptable floor — action required |

### 3. User-controlled label mode (optional enhancement)

A toggle or setting ("Export for: Engineering / Stakeholder") that controls whether
the export uses engineering labels or human labels. Engineering mode preserves
backwards compatibility for automated pipelines; stakeholder mode uses the renamed
headers. Default is stakeholder mode for manual downloads.

---

## Impact

- **Without this:** HR and QA stakeholders misread or return the export; an engineer
  must act as translator on every review cycle, adding lead time.
- **With this:** a non-technical reviewer can open the CSV, read the headers, consult
  the data dictionary, and produce feedback without intermediary — cutting one
  round-trip per review cycle.

---

## Acceptance Criteria

- [ ] The CSV/XLSX stakeholder export uses the human-friendly column headers defined
      above; engineering labels do not appear in the stakeholder export.
- [ ] A data dictionary is included with every stakeholder export (second sheet in
      Excel, companion CSV in ZIP).
- [ ] All three verdict values (`pass`, `warn`, `fail`) are defined in the data
      dictionary with operational meanings.
- [ ] An "engineering labels" export option (or toggle) retains the original column
      names to avoid breaking automated integrations.
- [ ] The header mapping is defined in one place in the codebase (not inline in
      export functions) so it can be updated without touching multiple files.
- [ ] The `Result` column in the raw export and `Overall Result` column in the summary
      export (BL-002) use the same vocabulary and values.

---

## Relationship to Other Backlog Items

- **BL-002 (Summary export):** The summary export should use the same human-friendly
  headers. BL-002 and BL-003 should be designed and shipped together or BL-003 first,
  so the summary export is never released with engineering labels.
- **BL-001 (KB context display):** If KB context is added to exports (BL-001), any
  new columns for that feature should go through the same header-mapping config so
  they receive human-friendly names from the start.

---

## Open Questions

1. **Who owns the label mapping?** Should the mapping be editable by harness admins
   at runtime (stored in the database), or is it a static code-level config that
   requires a deployment to change?
2. **Localisation:** HR SMEs at some sites may need non-English column headers. Is
   this a future concern or a day-one requirement?
3. **Backwards compatibility:** automated pipelines (CI scripts, data warehouse
   connectors) that consume the current engineering-labelled CSV will break if we
   change the default. How many such integrations exist and who owns them?

---

## Candidate Solutions (to be iterated)

_See iteration session for full analysis._

- **Option A — Static mapping in a config module:** a Python dict or YAML file maps
  internal field names to display names. All export functions import this dict.
  Simple, version-controlled, zero runtime cost.
- **Option B — Admin-editable mapping in the database:** harness admins can rename
  columns via a settings UI. Flexible, but adds UI surface and a schema migration.
- **Option C — Export profile system:** define named export profiles (e.g.,
  `engineering`, `hr-review`, `compliance`) each with their own header mapping and
  included fields. Users pick a profile at download time. Most flexible, most
  implementation effort.
- **Option D — Post-process with a template:** export the raw CSV as-is and provide
  a downloadable Excel macro or Power Query template that transforms headers on open.
  Zero backend changes, but fragile and requires Excel; does not address JSON exports.
