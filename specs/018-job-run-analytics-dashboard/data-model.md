# Data Model: Job Run Analytics Dashboard (018)

**Generated**: 2026-07-08 | **Plan**: [plan.md](plan.md)

---

## Overview

Feature 018 introduces no new database tables and requires no Alembic migration. All analytics are computed at page-load time from existing `utterance` and `evaluation_result` table data. The data model for this feature consists entirely of Python in-memory structures defined in `src/harness/ui/detail/analytics.py`.

---

## Updated Evaluation Contract (evaluation_scores JSON column)

The `evaluation_result.evaluation_scores` JSON column stores a list of parameter score entries. Feature 018 makes the `verdict` field optional — the column now accepts two valid entry shapes:

### v1 Shape (existing, deployed)
```json
{
  "parameter_name": "Groundedness",
  "score": 0.91,
  "reasoning": "Response fully grounded in supplied content."
}
```

### v2 Shape (new, upgraded evaluators)
```json
{
  "parameter_name": "Groundedness",
  "score": 0.91,
  "verdict": "Pass",
  "reasoning": "Response fully grounded in supplied content."
}
```

**Rules**:
- `verdict` is optional. A missing key is not an error.
- No other fields change. Existing casing is preserved.
- No DB schema change. The JSON column is additive.
- The harness write path is unchanged. New `verdict` fields pass through transparently.

---

## Analytics Engine Structures (`analytics.py`)

All structures are Python `dataclasses` with `frozen=True` for safe passing to Jinja2 templates.

---

### ScoreEntry

Input unit consumed by the engine. One `ScoreEntry` per utterance per parameter.

```python
@dataclass(frozen=True)
class ScoreEntry:
    parameter_name: str          # from evaluation_scores[n].parameter_name
    score: float                 # from evaluation_scores[n].score
    reasoning: str               # from evaluation_scores[n].reasoning
    verdict: str | None          # from evaluation_scores[n].verdict — None when absent (v1)
    overall_verdict: str | None  # from EvaluationResult.evaluation_verdict
    error: bool                  # True when EvaluationResult.error_status == 'failed'
```

**Notes**:
- Error rows (`error=True`) contribute to `error_count` only; they are excluded from all score and verdict metrics.
- The caller (route handler via `view.score_entries_from_utterances()`) is responsible for mapping ORM objects to this shape before calling the engine.

---

### VerdictCount

One instance per distinct verdict value in a distribution.

```python
@dataclass(frozen=True)
class VerdictCount:
    verdict: str     # e.g. "Pass", "Warning", "Fail" — verbatim from stored data
    count: int       # number of entries carrying this verdict
    pct: float       # percentage of contributing entries (0.0–100.0); rounded to 1 decimal
```

---

### HistogramBucket

One instance per bucket in the 10-bucket histogram for a parameter.

```python
@dataclass(frozen=True)
class HistogramBucket:
    index: int          # 0..9 (left to right)
    raw_low: float      # raw score value at the normalised bucket start boundary
    raw_high: float     # raw score value at the normalised bucket end boundary
    count: int          # utterances whose normalised score falls in this bucket
    sigma_low: float    # normalised x-position of (mean - 1σ); clamped to [0.0, 1.0]
    sigma_high: float   # normalised x-position of (mean + 1σ); clamped to [0.0, 1.0]
```

**Notes**:
- Bucket boundaries: `[0.0–0.1), [0.1–0.2), …, [0.9–1.0]`. Score of exactly 1.0 → bucket 9.
- `sigma_low` and `sigma_high` are identical across all 10 buckets for a given parameter (they are per-parameter, not per-bucket). The template reads them from `buckets[0]` and renders the σ band once.
- When `min == max` (all scores identical): all scores → bucket 4 (centre); `raw_low == raw_high == min`; `sigma_low == sigma_high == 0.5`.

---

### ParameterStats

One instance per discovered parameter. Produced by the engine for each parameter in `evaluatorDeclaredScoringDimensions` order, then any unexpected parameters.

```python
@dataclass(frozen=True)
class ParameterStats:
    parameter_name: str                          # display label (verbatim from data)
    parameter_id: str                            # derived slug: lowercase, spaces→underscores
    mean: float                                  # arithmetic mean of scores (raw)
    median: float                                # median of scores (raw)
    min: float                                   # minimum score (raw)
    max: float                                   # maximum score (raw)
    range: float                                 # max - min (raw)
    stddev: float                                # population stddev via statistics.pstdev() (raw)
    histogram_buckets: tuple[HistogramBucket, ...] # always 10 entries
    verdict_distribution: tuple[VerdictCount, ...] | None  # None when no v2 verdict data present
    verdict_coverage: int | None                 # count of entries that contributed to verdict_distribution; None when verdict_distribution is None
    is_unexpected: bool                          # True if not in declared dimensions list
```

---

### RunAnalytics

Top-level output of the engine. Caller-agnostic — used by both the batch job route handler (018) and the live chat analytics route handler (019).

```python
@dataclass(frozen=True)
class RunAnalytics:
    overall_mean_score: float | None             # None when evaluated_count == 0
    overall_verdict_distribution: tuple[VerdictCount, ...]  # empty tuple when no verdicts
    parameters: tuple[ParameterStats, ...]       # in declared order then unexpected
    evaluated_count: int                         # utterances/turns with valid results
    error_count: int                             # utterances/turns with error_status='failed'
```

---

## Engine Function Signature

Defined in `src/harness/ui/detail/analytics.py`. No ORM imports; no FastAPI imports; no Jinja2 imports.

```python
def compute_analytics(
    entries: list[ScoreEntry],
    declared_dims: list[str],
) -> RunAnalytics:
    """
    Aggregate ScoreEntry list into RunAnalytics.

    entries       — all score entries for the job/session (including error rows)
    declared_dims — ordered list of declared parameter names from the job/session snapshot
    """
    ...
```

**Computation steps** (in order):

1. Partition entries: `valid = [e for e in entries if not e.error]`; `error_count = sum(e.error for e in entries)`
2. `evaluated_count = len({e for e in valid})` — count of distinct utterances with ≥1 valid score entry
3. `overall_mean_score`: mean of all `e.score` for `e in valid`; `None` if `valid` is empty
4. `overall_verdict_distribution`: count+pct of `e.overall_verdict` for `e in valid` where `e.overall_verdict` is not None; deduplicated per utterance (use first occurrence per utterance to avoid double-counting multi-parameter rows)
5. Per parameter (in `declared_dims` order, then unexpected):
   - Collect `param_scores = [e.score for e in valid if e.parameter_name == name]`
   - Compute mean, median, min, max, range, stddev using `statistics` module
   - Normalise scores → build histogram buckets
   - Build verdict_distribution from `[e.verdict for e in valid if e.parameter_name == name and e.verdict is not None]`

---

## View Layer Additions (`view.py`)

### score_entries_from_utterances

```python
def score_entries_from_utterances(
    utterances: list[Utterance],
) -> list[ScoreEntry]:
    """Map ORM Utterance list (with evaluation_result relationship) to ScoreEntry list."""
```

Maps each `utterance.evaluation_result.evaluation_scores` entry to a `ScoreEntry`. Handles `None` evaluation_result, `None` evaluation_scores, and missing `verdict` key in entries.

### results_csv_builder

```python
def results_csv_builder(
    job: Job,
    utterances: list[Utterance],
) -> tuple[str, str]:
    """Build long-format results CSV. Returns (filename, csv_body)."""
```

Filename: `{source_csv_name_without_ext}-results.csv` (fallback: `job-{job_id[:8]}-results.csv`).
One row per utterance-parameter pair. Schema per FR-023.

### results_json_builder

```python
def results_json_builder(
    job: Job,
    utterances: list[Utterance],
) -> tuple[str, str]:
    """Build nested-by-utterance results JSON. Returns (filename, json_body)."""
```

Filename: `{source_csv_name_without_ext}-results.json` (fallback: `job-{job_id[:8]}-results.json`).
Array of utterance objects with nested parameters. Schema per FR-024.

---

## Template Context Additions

The `job_detail` route handler passes the following additional keys to `detail/index.html`:

| Key | Type | Description |
|---|---|---|
| `analytics` | `RunAnalytics \| None` | `None` when `total_utterance_count > 5000` or job has no utterances yet |
| `analytics_skipped` | `bool` | `True` when 5K guard triggered (FR-031) |
| `analytics_empty` | `bool` | `True` when `evaluated_count == 0` and `analytics_skipped` is `False` (FR-030) |

The template checks `analytics_skipped` first (shows unavailable message), then `analytics_empty` (shows empty-state placeholder), then renders the full `analytics` object.
