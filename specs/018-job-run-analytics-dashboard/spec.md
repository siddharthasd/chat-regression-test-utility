# Feature Specification: Job Run Analytics Dashboard (Module 18)

**Feature Branch**: `018-job-run-analytics-dashboard`

**Created**: 2026-07-08

**Status**: Draft

**Input**: Design decisions locked in session 2026-07-08. The dashboard sits inside the existing Job Detail page and replaces its current layout (three Bootstrap cards + flat table) with a single scrolling analytical report view. It renders dynamically from the evaluator output contract — no evaluator-specific code is permitted.

> **Parent context**: This module extends `specs/004-job-detail-view`. All FR- numbers and user stories from `004` remain in force unless explicitly superseded here. The evaluation contract is defined by `specs/006-evaluation-contract` and the reference document `references/Evaluator_Contract_Specification_MVP.md`. The analytics engine must be metadata-driven and must not contain evaluator-specific logic (per that document's locked principle §2.1).

---

## Clarifications

### Session 2026-07-08 — Design decisions locked

**Layout:**
- Q: How does the dashboard sit inside the detail page? → A: The existing three-card + table layout is replaced by a single scrolling view with a sticky left-hand sidebar containing section anchor links and action buttons. No tab strip. No sub-navigation inside the dashboard. Sections flow top-to-bottom: Job Overview → Parameter Breakdown → Result Explorer.

**Executive Summary and Evaluator Breakdown sections:**
- Q: Should the dashboard include an Executive Summary section and an Evaluator Breakdown section as described in `Evaluator_Contract_Specification_MVP.md §12`? → A: Both dropped for MVP. The Evaluator Breakdown is out of scope because multi-evaluator support is deferred. The Executive Summary is dropped in favour of folding its key metrics (overall verdict distribution, overall mean score) directly into the Job Overview section. The Evaluator Breakdown section is an explicitly named future extension point.

**Contract backward compatibility:**
- Q: The existing deployed evaluator contract (`evaluation_scores` entries containing `parameter_name`, `score`, `reasoning`) does not include per-parameter `verdict`. How should the dashboard handle this? → A: Path B — make per-parameter `verdict` optional in the contract. Add `verdict` as an optional field to each `evaluation_scores` entry. No other field changes: existing casing (`parameter_name`) is preserved, no `parameterId` field is added (it is derived at read time). No DB schema migration, no write-path changes. The dashboard handles both data vintages: when per-parameter `verdict` is absent, the verdict distribution tile for that parameter renders a visible "not available" placeholder rather than being hidden or silently omitted.

**Metrics:**
- Q: What metrics are computed per parameter? → A: Mean, Median, Min, Max, Range (max − min), Population Standard Deviation (σ). All stat tiles display raw values as emitted by the evaluator. Normalisation is a display-only concern for histogram rendering only.

**Standard deviation presentation:**
- Q: How is σ presented? → A: As a stat tile showing the raw σ value, and as ±1σ band markers drawn on the histogram. ±2σ bands are not shown in MVP.

**Histogram:**
- Q: What bucketing strategy for the histogram? → A: 10 fixed equal-width buckets across the normalised [0, 1] range. Scores are normalised per-parameter per-job using min-max: `normalised = (x − min) / (max − min)`. The x-axis labels show the actual raw values at each bucket boundary so the histogram is readable in the evaluator's native scale. When all scores for a parameter are identical (zero range), all scores are placed in the middle bucket.

**Exports:**
- Q: What export formats are required? → A: Three: (1) browser print via `window.print()` with a print stylesheet, (2) CSV download in long format (one row per utterance-parameter pair), (3) JSON download nested by utterance. The existing export card on the detail page is removed; its content is subsumed by the sidebar action buttons. CSV and JSON cover evaluated results only — the existing reconstructed-input CSV (from `004 FR-006`) is retired and replaced by the richer results downloads.

- Q: What is the CSV schema? → A: Long format. One row per utterance-parameter pair. Columns: `utteranceText`, `testId`, `chatbotResponse`, `overallVerdict`, `parameterName`, `score`, `verdict`, `reasoning`. The `verdict` cell is empty when per-parameter verdict is absent for that entry.

- Q: What is the JSON schema? → A: Nested by utterance. Each element contains: `utteranceText`, `testId`, `chatbotResponse`, `overallVerdict`, `errorStatus`, `errorStage`, and a `parameters` array. Each parameters entry contains: `parameter_name`, `score`, `reasoning`, and optionally `verdict` (key omitted when not present in stored data).

**Computation location:**
- Q: Where are aggregations computed? → A: Server-side at page load in the route handler. No separate analytics endpoint. No live refresh of analytics.

### Session 2026-07-08 (Round 2 — Clarifications)

- Q: What does the dashboard render when a job has zero valid evaluated results (all utterances errored)? → A: Option C — the Parameter Breakdown section body is replaced by a single informational placeholder message. The sidebar anchor link remains present but is visually muted.
- Q: Should analytics tiles refresh during the polling cycle on a running job? → A: No. Analytics are static after page load. The user must manually refresh the page to see updated analytics on a running job. Consistent with FR-028.
- Q: Should MVP include a performance guard for large jobs? → A: Yes — hard limit at 5,000 total utterances. Above this threshold, analytics computation is skipped entirely and a clear message is shown explaining the report is unavailable for jobs exceeding 5,000 utterances. Job Overview continues to render.
- Q: What is the filename convention for CSV and JSON exports, and are they available for non-terminal jobs? → A: Filename pattern is `{source_csv_name_without_ext}-results.csv` / `{source_csv_name_without_ext}-results.json`. Downloads are available ONLY when the job is in a terminal state (completed, failed, cancelled). No mid-job downloads. No `-partial` suffix (supersedes the availability clause in the original FR-025).
- Q: How should the histogram be rendered? → A: Vanilla CSS/HTML bars. No JavaScript chart library. Print-friendly by default.

---

## Updated Evaluation Contract

The `evaluation_scores` JSON column accepts two entry shapes. Both are valid. The dashboard reads both transparently.

**Legacy shape (v1 — no per-parameter verdict):**
```json
{
  "parameter_name": "Groundedness",
  "score": 0.91,
  "reasoning": "Response fully grounded in supplied content."
}
```

**Updated shape (v2 — with optional per-parameter verdict):**
```json
{
  "parameter_name": "Groundedness",
  "score": 0.91,
  "verdict": "Pass",
  "reasoning": "Response fully grounded in supplied content."
}
```

Rules:
- `verdict` is optional. Its absence is a valid state, not an error.
- All other fields and their casing are unchanged from the deployed contract.
- No other contract fields change in this module.
- The harness write path does not change. The new `verdict` field passes through the existing JSON column transparently when an upgraded evaluator emits it.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Understand the quality profile of a completed job run at a glance (Priority: P1)

A QA lead opens a completed job's detail page. Without scrolling, they see the Job Overview section: the existing job metadata, plus two new analytics tiles — overall verdict distribution showing how many utterances passed, warned, and failed, and an overall mean score across all evaluated parameters. They can immediately answer "did this run pass?" and "how far off are we?" before reading a single row.

**Why this priority**: The existing detail page shows only raw row data. The analytics layer is the primary value-add of this module and the first thing a user sees.

**Independent Test**: With a completed job of at least 20 utterances spanning all three verdict values, navigate to the detail page. Verify the Job Overview section displays overall verdict distribution counts and percentages that match a manual tally of `evaluation_verdict` values, and that the overall mean score matches the arithmetic mean of all `score` values across all `evaluation_scores` entries for the job.

**Acceptance Scenarios**:

1. **Given** a completed job with evaluated results, **When** the tester opens the detail page, **Then** the Job Overview section displays overall verdict distribution (one count and percentage per distinct verdict value observed) and overall mean score alongside all existing job metadata.
2. **Given** a job where some utterances errored before evaluation, **When** the tester views the Job Overview, **Then** the verdict distribution and mean score are computed only over utterances that have valid evaluation results; error rows do not contribute to either metric.
3. **Given** a running job (non-terminal), **When** the tester opens the detail page, **Then** the analytics tiles reflect the results evaluated so far at page-load time and are labelled to indicate the job is still in progress.

---

### User Story 2 — Inspect per-parameter quality statistics and score distribution (Priority: P1)

A QA engineer wants to know which evaluation parameters are performing poorly. They scroll to the Parameter Breakdown section, which shows one block per parameter. Each block has six stat tiles (Mean, Median, Min, Max, Range, σ) and a histogram with ±1σ bands. For parameters where the evaluator emits per-parameter verdicts, a verdict distribution tile is also present. The engineer identifies that "Completeness" has a mean of 0.61 and a long left tail on the histogram — investigation territory.

**Why this priority**: Parameter-level analytics is the reason this dashboard exists. Without it the feature delivers no insight beyond what the existing table already provides.

**Independent Test**: With a completed job whose evaluator emits at least three declared parameters with varied score distributions, verify each parameter block renders the correct stat tile values (computed independently against the raw data) and that the histogram bucket heights correspond to the actual score distribution.

**Acceptance Scenarios**:

1. **Given** a completed job with declared scoring dimensions, **When** the tester views the Parameter Breakdown section, **Then** one block renders per parameter in declared-dimension order, followed by any unexpected dimensions; each block shows Mean, Median, Min, Max, Range, and σ as stat tiles in raw values.
2. **Given** a parameter block, **When** the tester reads the histogram, **Then** the x-axis is labelled with raw score values at bucket boundaries, the histogram contains 10 fixed buckets, and ±1σ bands are visually marked relative to the mean.
3. **Given** a job whose evaluator emits per-parameter `verdict` (v2 contract), **When** the tester views a parameter block, **Then** a verdict distribution tile shows count and percentage per distinct verdict value for that parameter.
4. **Given** a job whose evaluator does not emit per-parameter `verdict` (v1 contract), **When** the tester views a parameter block, **Then** the verdict distribution tile renders a visible "not available" placeholder — it is not hidden and does not show a synthetic or inferred verdict.
5. **Given** a parameter with only one distinct score value across all utterances (zero variance), **When** the histogram renders, **Then** all scores appear in the middle bucket and the σ stat tile shows 0.

---

### User Story 3 — Export results for external analysis (Priority: P2)

A test manager wants to build a Power BI report from the run's results and share a printed summary with stakeholders. From the sidebar, they download the CSV (long format, one row per utterance-parameter pair) and the JSON (nested by utterance). They also click Print, which opens the browser print dialog with sidebar and chrome hidden, each section on a clean page break.

**Why this priority**: Exports make the analytics portable. Required for integration with existing reporting tooling (Excel, Power BI).

**Independent Test**: Download both formats from a completed job. Verify CSV column headers match the spec exactly, row count equals (utterance count × parameter count), and the JSON structure matches the locked schema. Print and verify sidebar chrome is suppressed.

**Acceptance Scenarios**:

1. **Given** a completed job, **When** the tester clicks Download CSV, **Then** a `.csv` file is downloaded containing one row per utterance-parameter pair with columns `utteranceText`, `testId`, `chatbotResponse`, `overallVerdict`, `parameterName`, `score`, `verdict`, `reasoning`; the `verdict` column is empty for parameters where per-parameter verdict is not stored.
2. **Given** a completed job, **When** the tester clicks Download JSON, **Then** a `.json` file is downloaded as an array of utterance objects each containing `utteranceText`, `testId`, `chatbotResponse`, `overallVerdict`, `errorStatus`, `errorStage`, and `parameters`; each parameter entry contains `parameter_name`, `score`, `reasoning`, and `verdict` only when stored.
3. **Given** a non-terminal job, **When** the tester downloads either format, **Then** the file contains all rows evaluated at time of click and the filename or a top-level field indicates the job was in progress at download time.
4. **Given** the tester clicks Print, **When** the browser print dialog opens, **Then** the print stylesheet suppresses the sidebar and page navigation chrome and inserts page breaks between the Job Overview, Parameter Breakdown, and Result Explorer sections.

---

### User Story 4 — Navigate the report with the sidebar (Priority: P2)

A tester on a large job scrolls to Parameter Breakdown, then wants to jump back to the top or down to the Result Explorer table. The sticky sidebar shows which section they are currently in (via scrollspy highlighting) and lets them jump to any section with a single click.

**Why this priority**: Without sidebar navigation, a long scrolling page with many parameters becomes unwieldy.

**Independent Test**: On a job with five or more declared parameters (making the page long), scroll through the page and verify the sidebar highlights the correct section anchor at each scroll position; verify each anchor link scrolls the page to the correct section.

**Acceptance Scenarios**:

1. **Given** the tester is viewing any section of the page, **When** they scroll, **Then** the sidebar remains visible (sticky) and the anchor link for the currently visible section is highlighted.
2. **Given** the tester clicks a sidebar anchor link, **When** the page responds, **Then** the viewport scrolls to the corresponding section smoothly.
3. **Given** the tester is on any scroll position, **When** they click Print, Download CSV, or Download JSON in the sidebar, **Then** the corresponding action fires without navigating away from the page.

---

## Functional Requirements

### Layout

**FR-001** The detail page MUST be restructured as a single scrolling view. The existing three-card layout (Job Details, Connector & Evaluator config, Export) is replaced. No tab strip is present on the page.

**FR-002** A sticky left-hand sidebar MUST be present at all scroll positions. The sidebar contains:
- Section anchor links: Job Overview, Parameter Breakdown, Result Explorer
- Action buttons: Print, Download CSV, Download JSON
The sidebar implements scrollspy: the anchor link for the section currently in the viewport is visually highlighted. The Download CSV and Download JSON buttons MUST be hidden or visually disabled for non-terminal jobs (queued, running, cancelling).

**FR-003** The existing export card (previously the third Bootstrap card) is removed. Its download affordances are subsumed by the sidebar action buttons per `FR-002`.

---

### Job Overview Section

**FR-004** The Job Overview section MUST display all metadata currently rendered by `004 FR-003` and `004 FR-004` (job name, description, status, timestamps, connector identity and configuration with secrets masked, evaluator identity and configuration with secrets masked, source CSV filename, aggregate counts). No existing metadata field is removed.

**FR-005** The Job Overview section MUST additionally display an overall verdict distribution tile. The tile shows, for each distinct `evaluation_verdict` value observed across the job's utterances, a count and a percentage of evaluated utterances. Utterances with `error_status = 'failed'` or null `evaluation_verdict` do not contribute to this distribution.

**FR-006** The Job Overview section MUST additionally display an overall mean score tile. The value is the arithmetic mean of all `score` values across all `evaluation_scores` entries for all utterances that have valid evaluation results. Raw value; not normalised.

---

### Analytics — Contract Reading

**FR-007** The analytics engine MUST read `evaluation_scores` entries in both the v1 shape (`parameter_name`, `score`, `reasoning`) and the v2 shape (`parameter_name`, `score`, `reasoning`, `verdict`). A missing `verdict` key is not an error condition.

**FR-008** `parameterId` is derived at read time from `parameter_name` by converting to lowercase and replacing spaces with underscores. It is not stored and is not required in the evaluator output.

**FR-009** Parameter discovery follows the existing `evaluatorDeclaredScoringDimensions` snapshot on the Job, in declared order. Parameters emitted by the evaluator that are not in the declared list are appended after the declared parameters, flagged as unexpected (preserving the existing `FR-007b` / `harnessAnnotations` behaviour from `004`).

---

### Analytics — Metric Computation

**FR-010** For each discovered parameter, the analytics engine MUST compute the following statistics across all evaluated utterances for that parameter:
- **Mean**: arithmetic mean of scores
- **Median**: middle value when scores are sorted; average of two middle values when count is even
- **Min**: minimum score
- **Max**: maximum score
- **Range**: Max − Min
- **σ (Population Standard Deviation)**: `sqrt( sum((x - mean)²) / N )`

All six values are in raw (un-normalised) form as emitted by the evaluator.

**FR-011** For histogram rendering only, scores for a given parameter MUST be normalised to [0, 1] using per-parameter per-job min-max normalisation: `normalised = (x − min) / (max − min)`. When min equals max (all scores identical), all scores are assigned a normalised value of 0.5.

**FR-012** The histogram for each parameter MUST use 10 fixed equal-width buckets across the normalised [0, 1] range (buckets: [0.0–0.1), [0.1–0.2), …, [0.9–1.0]). A score of exactly 1.0 is placed in the final bucket.

**FR-013** The histogram x-axis MUST be labelled with the raw score values that correspond to the normalised bucket boundaries. Labels are computed by inverting the normalisation: `raw = min + (normalised_boundary × (max − min))`.

**FR-014** The histogram MUST visually mark the ±1σ position relative to the mean as a vertical band or line indicator. The σ band is positioned using the normalised equivalent of `(mean ± σ)`, clamped to [0, 1].

---

### Parameter Breakdown Section

**FR-015** The Parameter Breakdown section MUST render one block per discovered parameter in the order defined by `FR-009`.

**FR-016** Each parameter block MUST display the six stat tiles defined in `FR-010` (Mean, Median, Min, Max, Range, σ) as prominent labelled values.

**FR-017** Each parameter block MUST display the histogram as defined in `FR-012`, `FR-013`, and `FR-014`. The histogram MUST be rendered using vanilla CSS/HTML bars with no JavaScript chart library dependency.

**FR-018** Each parameter block MUST display a verdict distribution tile when per-parameter `verdict` data is present. The tile shows, for each distinct verdict value observed for that parameter, a count and percentage. Only entries that carry a `verdict` value contribute to the distribution; partially-upgraded data (some entries have `verdict`, some do not) is valid — the tile shows the count of contributing entries.

**FR-019** When no `evaluation_scores` entry for a parameter carries a `verdict` value, the verdict distribution tile MUST render a visible "not available" placeholder in the position where the tile would appear. The placeholder MUST NOT be hidden, and MUST NOT display a synthetic or inferred verdict derived from the overall `evaluation_verdict` or from score thresholds.

### Metric Explanations

**FR-032** Each stat tile in a parameter block MUST display an info icon (ⓘ) adjacent to the metric label. On hover (desktop) or tap (touch), the icon MUST show a tooltip or popover containing the canonical explanation for that metric as defined in the Metric Explanations section below. The tooltip MUST be dismissible and MUST NOT permanently obscure adjacent content.

**FR-033** The Parameter Breakdown section MUST include a collapsible "How to read this report" guide panel positioned before the first parameter block. The panel MUST:
- Be expanded by default on first page load.
- Collapse on user interaction and remain collapsed for the duration of the browser session (via `sessionStorage`).
- Contain an explanation of each metric (Mean, Median, Min, Max, Range, σ, Score Distribution, Verdict Distribution) using the canonical copy defined in the Metric Explanations section below.

**FR-034** The Overall Mean Score tile and Overall Verdict Distribution tile in the Job Overview section MUST each display an info icon (ⓘ) adjacent to the tile label. On hover or tap, the icon MUST show a tooltip containing the canonical explanation defined in the Metric Explanations section below.

---

### Result Explorer Section

**FR-020** The Result Explorer section is the existing utterance results table from `004` with all existing functionality preserved: sort, verdict filter, error-only filter, testId filter, free-text search, "Visible: N of M" indicator, row expand with trace artifacts.

**FR-021** When a score cell in the Result Explorer table contains an entry with a `verdict` value (v2 contract), the verdict MUST be displayed inline alongside the score and reasoning within that score cell. When `verdict` is absent from the entry, the score cell renders as it does today (score + reasoning only).

---

### Exports

**FR-022** The Print action MUST call `window.print()`. A dedicated print stylesheet MUST:
- Hide the sidebar and all page navigation chrome.
- Insert a page break before the Parameter Breakdown section and before the Result Explorer section.
- Render stat tiles and histograms in a print-legible form (no interactive-only elements).

**FR-023** The Download CSV action MUST produce a `.csv` file in long format. The filename MUST follow the pattern `{source_csv_name_without_ext}-results.csv` where `source_csv_name_without_ext` is the source CSV filename with its `.csv` extension stripped (or `job-{job_id[:8]}` when no source filename is present). Schema:

| Column | Source |
|---|---|
| `utteranceText` | `Utterance.utterance_text` |
| `testId` | `Utterance.test_id` |
| `chatbotResponse` | `normalized_contract.chatbotResponse.normalizedText` |
| `overallVerdict` | `EvaluationResult.evaluation_verdict` |
| `parameterName` | `evaluation_scores[n].parameter_name` |
| `score` | `evaluation_scores[n].score` |
| `verdict` | `evaluation_scores[n].verdict` — empty string when absent |
| `reasoning` | `evaluation_scores[n].reasoning` |

One row per utterance-parameter pair. Utterances with `error_status = 'failed'` are included with their error state in `overallVerdict` and empty parameter columns.

**FR-024** The Download JSON action MUST produce a `.json` file as a JSON array. The filename MUST follow the pattern `{source_csv_name_without_ext}-results.json` using the same base name derivation as `FR-023`. Each element represents one utterance:

```json
{
  "utteranceText": "string",
  "testId": "string",
  "chatbotResponse": "string | null",
  "overallVerdict": "string | null",
  "errorStatus": "string | null",
  "errorStage": "string | null",
  "parameters": [
    {
      "parameter_name": "string",
      "score": number,
      "reasoning": "string",
      "verdict": "string"
    }
  ]
}
```

The `verdict` key inside each parameter object MUST be omitted (not set to null) when the stored entry does not contain it. The `parameters` array is empty for error rows.

**FR-025** CSV and JSON downloads are available ONLY when the job is in a terminal state (completed, failed, cancelled). The sidebar Download CSV and Download JSON buttons MUST be hidden or visually disabled for non-terminal jobs. No partial or mid-job downloads are supported for these formats.

---

### Sidebar Navigation

**FR-026** The sidebar MUST implement scrollspy: as the user scrolls, the sidebar anchor link for the section currently occupying the majority of the viewport MUST be visually distinguished (e.g., bold, accent colour, active class).

**FR-027** Clicking a sidebar anchor link MUST scroll the main content area to the top of the corresponding section. The sidebar itself does not scroll or navigate away.

---

### Computation

**FR-028** All metric aggregations (FR-010 through FR-014, FR-005, FR-006) MUST be computed server-side in the route handler at page load time. No client-side aggregation is required. No separate analytics API endpoint is introduced in this module.

**FR-029** Analytics computation MUST be scoped to utterances with valid evaluation results (`error_status` is null and `evaluation_scores` is non-null). Error rows contribute to the error count in Job Overview but not to any score or verdict metric.

**FR-030** When a job's `evaluated_count` is zero (all utterances errored or no results yet), the Parameter Breakdown section MUST replace its content body with a single informational placeholder message (e.g., "No evaluated results — all utterances resulted in errors."). The sidebar anchor link for Parameter Breakdown MUST remain present but MUST be rendered in a visually muted state. The Job Overview section continues to render normally.

**FR-031** When a job's `total_utterance_count` exceeds 5,000, analytics computation MUST be skipped entirely for that job. The Parameter Breakdown section MUST display a clear message stating that the analytics report is not available for jobs exceeding 5,000 utterances and directing the user to use the CSV or JSON export for further analysis. The Job Overview section (FR-004 through FR-006) continues to render. The 5,000 threshold applies to `total_utterance_count`, not `evaluated_count`.

---

## Analytics Projection (server-side data model)

The analytics computation is implemented as a **shared `RunAnalytics` engine** — a pure function that accepts a normalised list of scored entries and returns a `RunAnalytics` structure. The engine contains no knowledge of batch jobs, chat sessions, or any specific data model. Both the batch job route handler (this module) and the future live chat analytics route handler feed the engine the same normalised input shape and receive the same output.

### Shared Engine Input

Each call to the engine receives a flat list of score entries, one per unit-of-analysis (utterance or chat turn) per parameter:

```
ScoreEntry:
  parameter_name    str
  score             float
  reasoning         str
  verdict           str | None   — absent for v1 contract data
  overall_verdict   str | None   — job/turn-level verdict
  error             bool         — True if this unit errored before evaluation
```

The caller (route handler) is responsible for mapping the ORM model to this shape before calling the engine.

### Shared Engine Output

**`ParameterStats`** (one per discovered parameter):
```
parameterName        str       — display label
parameterId          str       — derived slug (lowercase, spaces → underscores)
mean                 float     — raw
median               float     — raw
min                  float     — raw
max                  float     — raw
range                float     — raw (max - min)
stddev               float     — raw population σ
histogram_buckets    list[HistogramBucket]   — 10 entries
verdict_distribution list[VerdictCount] | None  — None when no per-parameter verdict present
verdict_coverage     int | None  — count of entries that contributed to verdict_distribution
```

**`HistogramBucket`**:
```
index         int    — 0..9
raw_low       float  — raw value at normalised bucket start
raw_high      float  — raw value at normalised bucket end
count         int    — units whose normalised score falls in this bucket
sigma_low     float  — normalised position of mean - 1σ (for band rendering)
sigma_high    float  — normalised position of mean + 1σ (for band rendering)
```

**`VerdictCount`**:
```
verdict    str
count      int
pct        float   — percentage of contributing entries
```

**`RunAnalytics`** (top-level output, caller-agnostic):
```
overall_mean_score          float | None
overall_verdict_distribution list[VerdictCount]
parameters                  list[ParameterStats]
evaluated_count             int   — units with valid results
error_count                 int   — units with error_status = 'failed'
```

### Batch Job Mapping (this module)

The batch job route handler maps `Job → Utterance → EvaluationResult` to `ScoreEntry` list before calling the engine:

| `ScoreEntry` field | Source |
|---|---|
| `parameter_name` | `evaluation_scores[n].parameter_name` |
| `score` | `evaluation_scores[n].score` |
| `reasoning` | `evaluation_scores[n].reasoning` |
| `verdict` | `evaluation_scores[n].verdict` (optional) |
| `overall_verdict` | `EvaluationResult.evaluation_verdict` |
| `error` | `EvaluationResult.error_status == 'failed'` |

### Live Chat Session Mapping (future — 019)

The live chat analytics route handler will map `ChatSession → ChatTurn → ChatTurnResult` to the same `ScoreEntry` shape:

| `ScoreEntry` field | Source |
|---|---|
| `parameter_name` | `evaluationResult.parameters[n].parameter_name` |
| `score` | `evaluationResult.parameters[n].score` |
| `reasoning` | `evaluationResult.parameters[n].reasoning` |
| `verdict` | `evaluationResult.parameters[n].verdict` (optional) |
| `overall_verdict` | `evaluationResult.overallVerdict` |
| `error` | `ChatTurn.status == 'failed'` |

---

## Metric Explanations — Canonical Copy

The following copy is the canonical text for tooltips and the "How to read this report" guide panel. Implementers MUST use this exact wording. Do not paraphrase or abbreviate.

### Job Overview Metrics

**Overall Mean Score**
The average quality score across every response and every evaluation parameter in this run. Think of it as the overall grade for the chatbot — closer to the evaluator's maximum is better.

**Overall Verdict Distribution**
How the evaluator classified each response overall — for example, how many Passed, how many triggered a Warning, how many Failed. A quick summary of the run's quality at a glance.

### Parameter Breakdown Metrics

**Mean**
The average score for this parameter across all responses. Your baseline answer to "how well did the chatbot perform on this dimension?"

**Median**
The middle score when all responses are ranked from lowest to highest. If the median is noticeably lower than the mean, a small number of high-scoring responses are inflating the average. If the median is higher than the mean, a few poor responses are dragging it down. Mean and median close together means the scores are consistently spread.

**Min**
The lowest score any single response received on this parameter. Represents the worst-case performance observed in this run.

**Max**
The highest score any single response received on this parameter. Represents the best-case performance observed in this run.

**Range**
The gap between the best and worst scores (Max minus Min). A large range means performance was inconsistent — some responses scored well, others did not. A small range means the chatbot performed at a similar level across all responses.

**σ (Standard Deviation)**
Measures how spread out the scores are around the average. A low σ means most responses scored close to the mean — predictable, consistent behaviour. A high σ means scores varied widely — some responses were much better or worse than average. When comparing two parameters with the same mean, the one with the lower σ is more reliable.

**Score Distribution**
Shows where scores clustered across the full range. Bars to the right mean most responses scored high; bars to the left mean most scored low. A single tall bar means highly consistent scores; bars spread across the chart mean high variability. The shaded band marks where the middle approximately 68% of scores fall (±1 standard deviation from the mean) — scores outside this band are outliers worth investigating.

**Verdict Distribution**
How the evaluator classified individual responses for this specific parameter — for example, how many were rated Pass, Warning, or Fail. Tells you whether quality issues on this parameter are isolated incidents or a systematic pattern. Shown only when the evaluator provides per-parameter verdicts; otherwise displayed as "not available."

---

## Non-Goals (MVP)

- Multi-evaluator support. The analytics engine treats all `evaluation_scores` as belonging to a single evaluator. The Evaluator Breakdown section is a named future extension point.
- Server-side PDF generation. Browser print is the only PDF path.
- Live refresh of analytics. Analytics are computed once at page load.
- Per-run comparison across job runs.
- AI-generated analytical narratives.
- Non-numeric parameter types (Boolean, categorical, ordinal) — deferred per `Evaluator_Contract_Specification_MVP.md §13`.
- Custom aggregation methods or evaluator-specific visualisations.
- Normalisation of stat tile values — stat tiles always display raw evaluator-emitted scores.
- Live chat session analytics page — the `RunAnalytics` engine defined in this module is designed for reuse, but the live chat analytics surface (`/chat/{id}/analytics`) is a separate delivery specified in `specs/019-live-chat-analytics`.
