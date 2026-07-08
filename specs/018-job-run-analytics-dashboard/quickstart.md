# Developer Quickstart: Job Run Analytics Dashboard (018)

**Generated**: 2026-07-08 | **Plan**: [plan.md](plan.md)

---

## Prerequisites

Standard project setup (Python 3.11, virtualenv, existing DB). No new dependencies are introduced by this feature — `statistics` and `math` are Python stdlib.

```powershell
# From repo root — standard setup, already done if working on other features
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

No Alembic migration is needed. The database schema does not change.

---

## Key Files to Know

| File | Role |
|---|---|
| `src/harness/ui/detail/analytics.py` | **NEW** — RunAnalytics engine. Pure functions. No ORM. Start here. |
| `src/harness/ui/detail/view.py` | **EXTEND** — Add `score_entries_from_utterances()`, `results_csv_builder()`, `results_json_builder()`; update `_score_cells()` to pass through `verdict`. |
| `src/harness/ui/detail/routes.py` | **EXTEND** — Call analytics engine in `job_detail`; add two new download routes; remove `download_csv`. |
| `src/harness/ui/detail/templates/detail/index.html` | **REPLACE** — Full layout rewrite: sidebar, Job Overview tiles, Parameter Breakdown, Result Explorer. |
| `src/harness/ui/static/harness.css` | **EXTEND** — Add sidebar, stat-tile, histogram, σ-band, info-icon, and print CSS. |
| `tests/unit/detail/test_analytics.py` | **NEW** — Unit tests for the analytics engine. No DB fixture needed. |
| `tests/integration/test_detail_ui.py` | **EXTEND** — New test cases for analytics sections and downloads. |

---

## Implementation Order

Build in this order to keep tests green at each step.

### Step 1 — analytics.py (pure engine, fully testable immediately)

Create `src/harness/ui/detail/analytics.py` with:
- `ScoreEntry`, `VerdictCount`, `HistogramBucket`, `ParameterStats`, `RunAnalytics` dataclasses
- `compute_analytics(entries, declared_dims) -> RunAnalytics`
- Helper: `_derive_parameter_id(name: str) -> str` (lowercase + spaces→underscores)
- Helper: `_normalise(scores: list[float]) -> list[float]` (min-max; zero-range → 0.5 for all)
- Helper: `_build_histogram(normalised: list[float], raw_min, raw_max, mean, stddev) -> tuple[HistogramBucket, ...]`
- Helper: `_build_verdict_dist(verdicts: list[str]) -> tuple[VerdictCount, ...] | None`

Write `tests/unit/detail/test_analytics.py` at the same time. No DB needed — pass raw `ScoreEntry` lists directly.

Key edge cases to test:
- Single utterance (σ = 0, range = 0, all scores in middle bucket)
- All scores identical (zero-range histogram)
- Mix of v1 (no verdict) and v2 (with verdict) entries for the same parameter
- Error entries excluded from metrics but counted in `error_count`
- `total_utterance_count > 5000` guard (route-level, not engine-level — test in integration)
- `evaluated_count == 0` (engine returns `RunAnalytics` with empty parameters; route sets `analytics_empty=True`)
- Overall verdict deduplication (one utterance, multiple parameters — overall verdict counted once)

### Step 2 — view.py additions

Add to `src/harness/ui/detail/view.py`:

```python
def score_entries_from_utterances(utterances: list[Utterance]) -> list[ScoreEntry]:
    """Map ORM Utterance list to ScoreEntry list for the analytics engine."""
    entries = []
    for u in utterances:
        result = u.evaluation_result
        is_error = bool(result and result.error_status == "failed") or result is None
        overall_verdict = result.evaluation_verdict if result else None
        scores = (result.evaluation_scores or []) if result else []
        for s in scores:
            if not isinstance(s, dict):
                continue
            entries.append(ScoreEntry(
                parameter_name=s.get("parameter_name", ""),
                score=float(s.get("score", 0)),
                reasoning=s.get("reasoning") or "",
                verdict=s.get("verdict"),          # None for v1 entries
                overall_verdict=overall_verdict,
                error=is_error,
            ))
        if is_error and not scores:
            # Error row with no scores — represent as a single error entry
            entries.append(ScoreEntry(
                parameter_name="",
                score=0.0,
                reasoning="",
                verdict=None,
                overall_verdict=overall_verdict,
                error=True,
            ))
    return entries
```

Update `_score_cells()` to pass through `verdict` from v2 entries:
```python
cells.append({
    "name": d,
    "score": entry.get("score"),
    "reasoning": entry.get("reasoning") or "(none)",
    "verdict": entry.get("verdict"),     # None for v1 — template handles display
})
```

Add `results_csv_builder()` and `results_json_builder()` (see `data-model.md` for signatures).

### Step 3 — routes.py changes

In `job_detail`:
1. After loading utterances, call `score_entries_from_utterances(utterances)`
2. Apply the 5K guard and empty-state guard (see `contracts/ui-routes.md`)
3. Call `compute_analytics(entries, declared_dims)` if not guarded
4. Pass `analytics`, `analytics_skipped`, `analytics_empty` to the template

Add new download route handlers:
```python
@router.get("/jobs/{job_id}/download-results.csv")
async def download_results_csv(request: Request, job_id: str, user=Depends(require_auth)):
    ...  # 404 if not terminal; call view.results_csv_builder(); return Response

@router.get("/jobs/{job_id}/download-results.json")
async def download_results_json(request: Request, job_id: str, user=Depends(require_auth)):
    ...  # 404 if not terminal; call view.results_json_builder(); return Response
```

Remove the `download_csv` handler and its `@router.get("/jobs/{job_id}/download.csv")` decorator.

### Step 4 — CSS additions (harness.css)

Add new CSS classes. Do not remove or rename existing classes — the Result Explorer table reuses all existing `.verdict-*`, `.scores`, `.artifact pre`, `.harness-table` classes.

New classes needed:
```css
/* Sidebar layout */
.detail-layout { display: flex; gap: 1.5rem; }
.detail-sidebar { width: 220px; flex-shrink: 0; position: sticky; top: 1rem; height: fit-content; }
.detail-main { flex: 1; min-width: 0; }
.sidebar-nav a { display: block; padding: 0.25rem 0.75rem; color: var(--bs-secondary); text-decoration: none; border-left: 2px solid transparent; }
.sidebar-nav a.active { color: var(--bs-primary); border-left-color: var(--bs-primary); font-weight: 600; }
.sidebar-actions { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 1rem; }

/* Stat tiles */
.stat-tile-grid { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1rem; }
.stat-tile { background: var(--bs-light); border-radius: 0.375rem; padding: 0.75rem 1rem; min-width: 100px; }
.stat-tile .label { font-size: 0.75rem; color: var(--bs-secondary); margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.25rem; }
.stat-tile .value { font-size: 1.25rem; font-weight: 600; }

/* Histogram */
.histogram-wrap { position: relative; height: 120px; display: flex; align-items: flex-end; gap: 2px; border-bottom: 1px solid var(--bs-border-color); margin-bottom: 0.25rem; }
.histogram-bar { flex: 1; background: var(--bs-primary); opacity: 0.7; min-height: 2px; }
.sigma-band { position: absolute; bottom: 0; top: 0; background: rgba(255,193,7,0.2); pointer-events: none; }
.histogram-xaxis { display: flex; justify-content: space-between; font-size: 0.65rem; color: var(--bs-secondary); }

/* Info icon */
.info-icon { font-size: 0.7rem; color: var(--bs-secondary); cursor: help; vertical-align: middle; }

/* Guide panel */
.analytics-guide { background: var(--bs-info-bg-subtle); border: 1px solid var(--bs-info-border-subtle); border-radius: 0.375rem; padding: 1rem; margin-bottom: 1.5rem; font-size: 0.875rem; }

/* Print */
@media print {
  .detail-sidebar { display: none; }
  .detail-layout { display: block; }
  .detail-main { width: 100%; }
  .parameter-section { page-break-before: auto; }
  #section-parameter-breakdown { page-break-before: always; }
  #section-result-explorer { page-break-before: always; }
  .histogram-bar { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
```

### Step 5 — Template rewrite (index.html)

Replace `detail/templates/detail/index.html` with the new layout. Key structural outline:

```html
{% extends "base.html" %}
{% block content %}
<div class="detail-layout">

  {# ── Sidebar ── #}
  <aside class="detail-sidebar">
    <nav class="sidebar-nav" id="sidebar-nav">
      <a href="#section-job-overview">Job Overview</a>
      <a href="#section-parameter-breakdown" {% if analytics_empty %}class="text-muted"{% endif %}>
        Parameter Breakdown
      </a>
      <a href="#section-result-explorer">Result Explorer</a>
    </nav>
    <div class="sidebar-actions mt-3">
      <button onclick="window.print()" class="btn btn-sm btn-outline-secondary">Print</button>
      {% if meta.terminal %}
        <a href="/jobs/{{ meta.job_id }}/download-results.csv" class="btn btn-sm btn-outline-primary">Download CSV</a>
        <a href="/jobs/{{ meta.job_id }}/download-results.json" class="btn btn-sm btn-outline-primary">Download JSON</a>
      {% else %}
        <button class="btn btn-sm btn-outline-secondary" disabled title="Available after job completes">Download CSV</button>
        <button class="btn btn-sm btn-outline-secondary" disabled title="Available after job completes">Download JSON</button>
      {% endif %}
    </div>
  </aside>

  {# ── Main content ── #}
  <main class="detail-main">

    {# Section 1: Job Overview #}
    <section id="section-job-overview">
      <h2>Job Overview</h2>
      {# ... existing metadata cards condensed ... #}
      {# ... overall_verdict_distribution tile ... #}
      {# ... overall_mean_score tile ... #}
    </section>

    {# Section 2: Parameter Breakdown #}
    <section id="section-parameter-breakdown">
      <h2>Parameter Breakdown</h2>

      {% if analytics_skipped %}
        <div class="alert alert-warning">
          Analytics are not available for jobs with more than 5,000 utterances.
          Use Download CSV or Download JSON to analyse results externally.
        </div>

      {% elif analytics_empty %}
        <div class="alert alert-secondary">
          No evaluated results — all utterances resulted in errors.
        </div>

      {% else %}
        {# Collapsible guide panel #}
        <div class="analytics-guide" id="analytics-guide">
          <strong>How to read this report</strong>
          <button onclick="toggleGuide()" class="btn btn-sm float-end">Collapse</button>
          <div id="analytics-guide-body">
            {# ... canonical metric explanations ... #}
          </div>
        </div>

        {% for param in analytics.parameters %}
        <div class="parameter-section mb-4">
          <h3>{{ param.parameter_name }}{% if param.is_unexpected %} <small class="text-warning">(unexpected)</small>{% endif %}</h3>

          {# Stat tiles #}
          <div class="stat-tile-grid">
            {% for label, value in [("Mean", param.mean), ("Median", param.median),
                                    ("Min", param.min), ("Max", param.max),
                                    ("Range", param.range), ("σ", param.stddev)] %}
            <div class="stat-tile">
              <div class="label">{{ label }} <span class="info-icon" data-bs-toggle="tooltip" data-bs-title="{{ tooltip_copy[label] }}">ⓘ</span></div>
              <div class="value">{{ "%.4f"|format(value) }}</div>
            </div>
            {% endfor %}
          </div>

          {# Histogram #}
          <div class="histogram-wrap">
            {% set max_count = param.histogram_buckets | map(attribute='count') | max %}
            <div class="sigma-band" style="left: {{ (param.histogram_buckets[0].sigma_low * 100)|round(1) }}%; width: {{ ((param.histogram_buckets[0].sigma_high - param.histogram_buckets[0].sigma_low) * 100)|round(1) }}%;"></div>
            {% for bucket in param.histogram_buckets %}
            <div class="histogram-bar" style="height: {{ ((bucket.count / max_count * 100) if max_count > 0 else 0)|round(1) }}%;" title="[{{ '%.3f'|format(bucket.raw_low) }}–{{ '%.3f'|format(bucket.raw_high) }}]: {{ bucket.count }}"></div>
            {% endfor %}
          </div>
          <div class="histogram-xaxis">
            {% for bucket in param.histogram_buckets %}
            <span>{{ "%.2f"|format(bucket.raw_low) }}</span>
            {% endfor %}
            <span>{{ "%.2f"|format(param.histogram_buckets[-1].raw_high) }}</span>
          </div>

          {# Verdict distribution #}
          {% if param.verdict_distribution is none %}
            <p class="text-muted mt-2"><em>Verdict distribution not available — evaluator does not emit per-parameter verdicts.</em></p>
          {% else %}
            {# ... render verdict distribution tiles ... #}
          {% endif %}
        </div>
        {% endfor %}
      {% endif %}
    </section>

    {# Section 3: Result Explorer (existing table, unchanged) #}
    <section id="section-result-explorer">
      <h2>Result Explorer</h2>
      {# ... existing table markup preserved verbatim ... #}
    </section>

  </main>
</div>

<script>
// Scrollspy
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('#sidebar-nav a');
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      navLinks.forEach(a => a.classList.remove('active'));
      const active = document.querySelector(`#sidebar-nav a[href="#${entry.target.id}"]`);
      if (active) active.classList.add('active');
    }
  });
}, { threshold: 0.15 });
sections.forEach(s => observer.observe(s));

// Guide collapse
function toggleGuide() {
  const body = document.getElementById('analytics-guide-body');
  const collapsed = body.style.display === 'none';
  body.style.display = collapsed ? '' : 'none';
  sessionStorage.setItem('analytics-guide-collapsed', collapsed ? '0' : '1');
}
if (sessionStorage.getItem('analytics-guide-collapsed') === '1') {
  document.getElementById('analytics-guide-body').style.display = 'none';
}

// Bootstrap tooltips
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-bs-toggle="tooltip"]')
    .forEach(el => bootstrap.Tooltip.getOrCreateInstance(el));
});
</script>
{% endblock %}
```

---

## Running Tests

```powershell
# Unit tests for the analytics engine only (fast, no DB)
pytest tests/unit/detail/test_analytics.py -v

# All detail UI integration tests (includes existing + new 018 cases)
pytest tests/integration/test_detail_ui.py -v

# Full test suite
pytest
```

---

## Verifying the Feature Manually

1. Start the dev server: `uvicorn harness.ui:create_app --factory --reload`
2. Create a test job with a completed evaluation via the wizard
3. Navigate to `/jobs/{job_id}/detail`
4. Verify: sidebar sticks on scroll; analytics tiles appear in Job Overview; Parameter Breakdown shows one block per declared dimension; histogram bars are visible; σ band is visible; guide panel is expanded; collapsing guide persists within the session
5. Verify tooltip: hover the ⓘ icon on a stat tile — tooltip should appear with canonical copy
6. Verify downloads: for a completed job, click Download CSV and Download JSON; for a non-terminal job, verify buttons are disabled
7. Verify print: click Print — sidebar should be hidden; sections should have page breaks
8. Verify 5K guard: seed a job with `total_utterance_count = 5001` (or update directly in DB); verify analytics section shows the unavailability message
9. Verify empty state: seed a job where all utterances have `error_status = 'failed'`; verify the placeholder renders and the sidebar anchor is muted
