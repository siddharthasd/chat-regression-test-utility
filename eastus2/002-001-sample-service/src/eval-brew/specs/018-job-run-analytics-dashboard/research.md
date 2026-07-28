# Research: Job Run Analytics Dashboard (018)

**Generated**: 2026-07-08 | **Plan**: [plan.md](plan.md)

All decisions below were resolved during Phase 0 research against the existing codebase.

---

## Decision 1 — Analytics module placement

**Decision**: New `analytics.py` pure-function module within the existing `harness.ui.detail` package.

**Rationale**: Keeps all detail-page logic co-located. Pure functions (no ORM imports) make the module independently testable without a database fixture. Mirrors the existing pattern where `view.py` is a pure projection layer with no ORM dependencies. The engine is designed to be imported by feature 019's route handler as well, making the `harness.ui.detail.analytics` import path the canonical shared location.

**Alternatives considered**:
- Separate `harness.analytics` package — rejected: adds a new package with a single near-term consumer and forces a cross-package import for the detail route.
- Class-based `AnalyticsEngine` — rejected: stateless computation needs no instance state; plain functions are simpler and equally testable.

---

## Decision 2 — Standard deviation formula

**Decision**: Use `statistics.pstdev(scores)` from the Python stdlib for population standard deviation.

**Rationale**: Population stddev is correct here — the utterances in a job are the full population being analysed, not a sample drawn from a larger population. `statistics.pstdev()` handles the edge case of a single-element list (returns 0.0) without raising `ZeroDivisionError`. No new dependency: `statistics` is stdlib since Python 3.4.

**Formula equivalence**: `pstdev(x) = sqrt(sum((xi - mean)²) / N)` — matches the spec FR-010 definition exactly.

**Alternatives considered**:
- `numpy.std(ddof=0)` — rejected: adds a heavy numerical library for three arithmetic operations.
- `statistics.stdev()` (sample, `ddof=1`) — rejected: sample stddev is inappropriate when the full population is present; produces inflated values for small job sizes.
- Manual `math.sqrt(sum(...)/n)` — rejected: duplicates stdlib logic and requires manual edge-case handling.

---

## Decision 3 — Histogram rendering technology

**Decision**: Vanilla CSS `<div>` bars inside a fixed-height container. Each bar's height is `(bucket_count / max_bucket_count) * 100%`. The σ band is a positioned `<div>` with `left` and `width` set as percentages of the histogram container width (derived from normalised σ positions). X-axis labels are `<span>` elements positioned under each bucket boundary.

**Rationale**: No new JS or CSS library dependency. Works correctly in the print stylesheet without special rendering workarounds (CSS `@media print` fully supports percentage heights). Consistent with the project's no-build-step, no-bundler constraint.

**Alternatives considered**:
- Chart.js via CDN — rejected: new CDN dependency, non-trivial print CSS, requires JS canvas rendering which fails in some print contexts.
- Server-side inline SVG — rejected: complex Jinja2 string generation, SVG print rendering varies across browsers and print drivers.
- D3.js — rejected: heavyweight for a static bar chart with no interaction requirements beyond the σ band.

---

## Decision 4 — Scrollspy implementation

**Decision**: Vanilla JS `IntersectionObserver` watching each section's `<h2>` or `<section>` landmark element. When a section enters the viewport, the corresponding sidebar anchor receives an `active` class. The observer fires with `threshold: 0.15` so a section is considered active when 15% or more of it is visible.

**Rationale**: `IntersectionObserver` is available in all target browsers (Chrome 58+, Firefox 55+, Safari 12.1+). No library dependency. Consistent with the project's inline-JS approach. A `threshold` of 0.15 provides comfortable triggering without requiring the section to be fully visible.

**Alternatives considered**:
- Bootstrap 5 Scrollspy — rejected: requires the scroll container to be a specific element (`overflow-y: scroll`) rather than the browser window; conflicts with the full-page scroll layout specified in FR-001.
- Scroll event listener with `getBoundingClientRect` — rejected: less efficient than `IntersectionObserver`; triggers on every scroll frame.

---

## Decision 5 — Tooltip implementation

**Decision**: Bootstrap 5 tooltip component via `data-bs-toggle="tooltip"` and `data-bs-title` attributes on each info icon `<button>`. Initialised with `document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => bootstrap.Tooltip.getOrCreateInstance(el))` in a `DOMContentLoaded` listener.

**Rationale**: Bootstrap 5 is already loaded via CDN on every page. Tooltips require zero additional JS or CSS beyond what is already present. The Bootstrap tooltip API handles hover, focus, and click-to-open (touch) behaviour automatically.

**Alternatives considered**:
- Custom CSS `::after` tooltip — more work, less accessible (no focus state, no ARIA).
- Tippy.js — new CDN dependency for functionality already in Bootstrap.

---

## Decision 6 — "How to read" guide collapse persistence

**Decision**: Store guide open/closed state in `sessionStorage` under the key `analytics-guide-collapsed`. Read on page load to set initial state. Write on toggle.

**Rationale**: `sessionStorage` is cleared when the browser tab is closed. This means the guide re-opens on each new session — appropriate because new browser sessions may involve different users on a shared machine, and new testers should always see the guide. `localStorage` would persist indefinitely and prevent future first-time readers from seeing it.

**Alternatives considered**:
- `localStorage` — rejected: too persistent; would suppress the guide for all future testers on a shared machine.
- Server-side user preference — rejected: the project has no per-user preference storage; adding one for this alone is disproportionate.
- Cookie — rejected: requires server round-trip to read; overkill for a client-side toggle.

---

## Decision 7 — Download route paths and backward compatibility

**Decision**: Add two new routes:
- `GET /jobs/{job_id}/download-results.csv`
- `GET /jobs/{job_id}/download-results.json`

Remove the existing `GET /jobs/{job_id}/download.csv` route (`view.reconstruct_csv()`) and its handler. The old export card UI is also removed per FR-003.

**Rationale**: The new downloads have a fundamentally different schema (long-format evaluated results vs. reconstructed input utterances). Keeping the old route at the same path would silently change its output for any bookmarked or scripted consumers. The spec explicitly states the old format is "retired and replaced." Removing it cleanly prevents any ambiguity.

**Alternatives considered**:
- Redirect old route to new route — rejected: the schemas are incompatible; a redirect would deliver an unexpected payload to callers expecting the old format.
- Keep old route as-is alongside new routes — rejected: the spec retires it; keeping it creates permanent confusion about which route to use.

---

## Decision 8 — Analytics data access pattern

**Decision**: Reuse the existing `UtteranceRepository.get_by_job_ordered()` call already in the route handler. Extract `utterance.evaluation_result` from the SQLAlchemy relationship on each `Utterance` object (already lazy-loaded or can be joined). Pass the utterance list to a new `view.score_entries_from_utterances()` mapper before calling the analytics engine.

**Rationale**: The existing route handler already calls `get_by_job_ordered()` to build `all_rows`. Feeding this same list to the analytics engine adds zero extra DB queries. The ORM relationship `utterance.evaluation_result` is already populated by the existing query path. Adding a second `EvaluationResultRepository.get_by_job()` call would be redundant.

**Alternatives considered**:
- `EvaluationResultRepository.get_by_job()` — rejected: second query, unordered results, redundant with the utterance-relationship access already in the handler.
- Raw SQL aggregation in the DB layer — rejected: moves computation to the DB and prevents Python-level normalisation (min-max, σ bands); also harder to unit test.

---

## Decision 9 — Histogram σ band rendering

**Decision**: The σ band is a single `<div class="sigma-band">` absolutely positioned within the histogram container. Its `left` and `width` CSS properties are set inline from the template using the `sigma_low` and `sigma_high` values in `HistogramBucket[0]` (both values are the same across all buckets — they are properties of the parameter, not the individual bucket). Clamped to [0%, 100%].

**Rationale**: A single `<div>` overlay is simpler than per-bucket rendering. The σ band spans across bucket boundaries — it is a continuous region, not a per-bucket attribute. Placing it in `HistogramBucket[0]` (or on `ParameterStats` directly) and rendering it once keeps the template logic clean.

**Note for implementers**: The `sigma_low` and `sigma_high` fields on `HistogramBucket` are identical across all 10 buckets for a given parameter (they are per-parameter, not per-bucket). The template should read them from `parameter.histogram_buckets[0]` and render the band once. This redundancy in the data structure is intentional — it simplifies the template by keeping all rendering data on the bucket object.

**Alternatives considered**:
- Per-bucket shading (colour the bucket if it falls within ±1σ) — rejected: visually less precise; cannot represent fractional σ boundaries at bucket edges.
- SVG `<rect>` overlay — rejected: mixing SVG into a CSS-bar histogram creates layout complexity.

---

## Decision 10 — Minimum utterance count for analytics computation

**Decision**: Compute analytics for any `evaluated_count ≥ 1`. For `evaluated_count == 0`, show the empty-state placeholder (FR-030). For `total_utterance_count > 5000`, skip entirely (FR-031). No minimum evaluated count between 1 and 5000.

**Rationale**: Even a single evaluated utterance produces meaningful (if limited) stats — mean = min = max = the one score, range = 0, σ = 0. Suppressing analytics for small counts would be surprising to users running quick smoke tests. The spec does not define a minimum.

**Alternatives considered**:
- Minimum of 2 evaluated utterances (to make stddev non-trivial) — rejected: σ = 0 for a single score is accurate and should be displayed, not hidden.
- Minimum of 10 utterances — rejected: arbitrary; suppresses analytics for intentionally small test suites.
