# BL-002 — CSV Download: Per-Query Aggregated Summary Export

**Created:** 2026-08-07
**Status:** Backlog
**Area:** Results Export / CSV Download
**Stakeholders:** Business Reviewers, HR SMEs, QA Leads

---

## Problem Statement

The current CSV export produces one row per **query × dimension** combination. For a
job with 64 queries evaluated across 4 dimensions this produces 256 rows. Business
reviewers and HR SMEs need to open this file in Excel or Google Sheets, but the raw
format requires non-trivial pivoting or scripting before any query-level picture
emerges. Stakeholders who are not data-literate enough to pivot a flat table cannot
use the export at all.

There is also no single "verdict" column a reviewer can scan to triage which queries
need attention. To find all failing queries, a reviewer must manually identify which
`utteranceId` values have at least one `fail` row — across 256 rows, without a
rolled-up view.

---

## Current Behaviour

Export CSV structure (one row per utterance × dimension):

```
utteranceId, utteranceText, parameterName, score, verdict, ...
uuid-001,    "What is PTO?", accuracy,    0.9,   pass, ...
uuid-001,    "What is PTO?", relevance,   0.7,   warn, ...
uuid-001,    "What is PTO?", grounding,   0.85,  pass, ...
uuid-001,    "What is PTO?", completeness,0.6,   fail, ...
uuid-002,    "How do I apply for leave?", accuracy, ...
...
```

- 64 queries × 4 dimensions = **256 rows** minimum.
- Reviewer must group by `utteranceId` and read four rows per query to understand it.
- No single overall verdict per query is present; the worst dimension determines
  failure but this is not surfaced.

---

## Desired Behaviour

The export offers **two sheets / two files**:

### File 1 — Raw export (unchanged)
The existing per-row-per-dimension format, as today. No breaking change.

### File 2 — Summary export (new)
One row per query, with all dimension scores and an overall verdict in a single row.

Proposed summary row structure:

| Column | Description |
|---|---|
| `queryId` | The `testId` from the input CSV |
| `utteranceId` | Internal UUID |
| `userQuestion` | The utterance text |
| `overallVerdict` | Worst-case verdict across all dimensions (`fail` > `warn` > `pass`) |
| `accuracy_score` | Score for the accuracy dimension |
| `accuracy_verdict` | Verdict for the accuracy dimension |
| `relevance_score` | Score for the relevance dimension |
| `relevance_verdict` | Verdict for the relevance dimension |
| `grounding_score` | Score for the grounding dimension |
| `grounding_verdict` | Verdict for the grounding dimension |
| `completeness_score` | Score for the completeness dimension |
| `completeness_verdict` | Verdict for the completeness dimension |
| `failedDimensions` | Comma-separated list of dimension names that returned `fail` |
| `evaluationTimestamp` | Timestamp of the evaluation run |

> Dimension column names are dynamic — the harness generates columns for whatever
> dimensions the evaluator reported, not a hardcoded set of four.

When the job is downloaded, the UI offers:
- **Download Raw CSV** (existing behaviour)
- **Download Summary CSV** (new)
- **Download Both (ZIP)** (new — bundles raw + summary)

---

## Impact

- **Without this:** HR/QA stakeholders cannot read the export without Excel pivot skills;
  business sign-off on evaluation results is blocked or requires a data analyst
  intermediary.
- **With this:** a reviewer opens the summary file, filters `overallVerdict = fail`,
  and immediately sees which queries failed and which dimensions drove the failure —
  no pivot required.

---

## Acceptance Criteria

- [ ] A "Download Summary CSV" action is available on the job results page alongside
      the existing raw download.
- [ ] The summary CSV has exactly one row per query (utterance), regardless of how
      many dimensions the evaluator reported.
- [ ] `overallVerdict` is computed as the worst verdict across all dimensions
      (`fail` takes precedence over `warn`, which takes precedence over `pass`).
- [ ] Dimension columns are generated dynamically from the actual dimensions present
      in the results — the format is not hardcoded to four dimensions.
- [ ] `failedDimensions` lists only the dimension names whose verdict is `fail`
      (empty string if none).
- [ ] The existing raw CSV export is unchanged (no breaking change for existing
      integrations or automations).
- [ ] A "Download Both (ZIP)" option bundles both files in a single download.
- [ ] The summary CSV uses the human-friendly column headers defined in BL-003
      (the two backlog items are complementary and should ship together or in sequence).

---

## Open Questions

1. **Aggregation rule for score:** when collapsing dimensions to one row, should the
   summary show each dimension's score, or also an `averageScore` across all dimensions?
   Average can mislead (a 0.9 accuracy and 0.1 grounding averages to 0.5, which looks
   mediocre rather than failed).
2. **Partial results:** if a job completed with some rows errored (not scored), should
   errored rows appear in the summary with a special verdict (e.g., `error`), or be
   excluded?
3. **Server-side or client-side generation:** should the summary be generated on-demand
   by the backend (consistent, no browser memory limits) or computed in the browser from
   the raw export (simpler but breaks on very large jobs)?

---

## Candidate Solutions (to be iterated)

_See iteration session for full analysis._

- **Option A — Backend pivot endpoint:** add `GET /api/jobs/{id}/export/summary`
  that runs the pivot server-side and streams a CSV. Clean, no client memory limits,
  cacheable.
- **Option B — Client-side pivot:** download the raw JSON results to the browser
  and pivot in JavaScript before offering the download. Zero backend changes, but
  limited to jobs that fit in browser memory (~tens of thousands of rows).
- **Option C — Pre-computed summary table:** persist a denormalised summary row in
  the database when each job completes. Export reads this table directly. Fast reads,
  but adds write complexity and a schema migration.
- **Option D — Export as Excel with two sheets:** generate an `.xlsx` file with a
  "Raw" sheet and a "Summary" sheet using `openpyxl` or `xlsxwriter`. Eliminates
  the two-file UX concern, but adds a binary dependency and deviates from the
  existing CSV-only export.
