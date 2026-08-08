# BL-005 Implementation Plan — Dimension Declaration: Cap, Scale Bounds, and Registration-Time Validation

**Spec:** `docs/backlog/BL-005-dimension-declaration-constraints.md`
**Created:** 2026-08-08

---

## Architecture Notes (Read Before Implementing)

### How the evaluator config snapshot works

The evaluator config is NOT stored as a JSON blob. It is stored as six individual nullable
ORM columns on the `Job` model (`evaluator_endpoint_url`, `evaluator_auth_descriptor`,
`evaluator_timeout_seconds`, `evaluator_declared_scoring_dimensions`, etc.). The function
`_evaluator_snapshot(job)` in `pipeline.py` reads these individual columns and constructs
an `EvaluatorSnapshot` dataclass. All new fields follow the same `job.evaluator_*` pattern.

### Key interfaces confirmed against real code

- `EvaluatorSnapshot` — frozen dataclass in `src/harness/evaluator/result.py`; only
  constructor is `_evaluator_snapshot()` in `pipeline.py`
- `parse_evaluator_form` — returns `tuple[dict | None, dict[str, str]]` (payload, errors);
  NOT a plain dict
- `compute_analytics(entries, declared_dims)` — called from two modules:
  `detail/routes.py:151` and `chat_session/routes.py:815`
- `_analytics_context` — called from two places in `detail/routes.py`:
  `job_detail` (line 183) and `_rerender_error` (line 401)
- `score_entries_from_utterances` in `detail/view.py:383` and `score_entries_from_turns`
  in `chat_session/view.py:138` both have the `float(score or 0.0)` falsy-zero coercion

---

## Dependency Order

```
Phase 1 (Migration — both tables)
   └─ Phase 2 (ORM Models — EvaluationAgentRegistration + Job)
         └─ Phase 3 (Repositories — types, evaluator_registration, job)
               ├─ Phase 4 (EvaluatorSnapshot + pipeline.py)
               │     └─ Phase 10 (Range Validation — client.py)
               ├─ Phase 6 (Service — service.py)
               │     └─ Phase 7 (Routes — evaluator_registry/routes.py)
               │           ├─ Phase 8 (Form Template)
               │           └─ Phase 9 (Detail Template — new file)
               └─ Phase 12 (View Layer — labels, exports, data dict)
                     └─ Phase 13 (Detail route context + results table header)

Phase 5 (forms.py) — no ORM dependency; parallelisable with Phases 1–4
Phase 11 (Analytics) — depends on Phase 3 (job columns) + ScoreEntry change in Phase 11a
Phase 14 (Tests) — written alongside each phase or as a final sweep
```

---

## Phase 1 — Database Migration

**File (new):** `src/harness/persistence/migrations/versions/0010_add_evaluator_scale.py`

```python
revision: str = "0010"
down_revision: str | None = "0009"
```

**Two tables, four columns total.**

`evaluation_agent_registration` (two columns):
- `score_scale_min` — `Float`, nullable
- `score_scale_max` — `Float`, nullable

`job` (two columns):
- `evaluator_score_scale_min` — `Float`, nullable
- `evaluator_score_scale_max` — `Float`, nullable

Follow the inspect-before-add pattern from `0009_add_conversation_id_to_chat_session.py`:
use `inspect(op.get_bind()).get_columns(table_name)` to check for column existence before
calling `op.add_column`. This makes the migration idempotent on re-run.

`downgrade()` drops the four columns conditionally (same inspect-before-drop pattern).

No data backfill. All four columns default to `NULL` on existing rows.

**Gate:** `alembic upgrade head` succeeds; `psql \d evaluation_agent_registration` and
`psql \d job` both show the new nullable float columns.

---

## Phase 2 — ORM Model Updates

**Dependency:** Phase 1.

### 2a. `src/harness/persistence/models/evaluator_registration.py`

Add after `declared_scoring_dimensions`:

```python
score_scale_min: Mapped[float | None] = mapped_column(Float, nullable=True)
score_scale_max: Mapped[float | None] = mapped_column(Float, nullable=True)
```

### 2b. `src/harness/persistence/models/job.py`

Add after `evaluator_declared_scoring_dimensions`:

```python
evaluator_score_scale_min: Mapped[float | None] = mapped_column(Float, nullable=True)
evaluator_score_scale_max: Mapped[float | None] = mapped_column(Float, nullable=True)
```

Add both names to `SNAPSHOT_FIELDS` (the `frozenset[str]` at line 22):

```python
SNAPSHOT_FIELDS: frozenset[str] = frozenset({
    ...,                              # existing fields unchanged
    "evaluator_score_scale_min",
    "evaluator_score_scale_max",
})
```

**Gate:** Reading `.score_scale_min` on an existing `EvaluationAgentRegistration` returns
`None`. Reading `.evaluator_score_scale_min` on an existing `Job` returns `None`.

---

## Phase 3 — Repository Layer

**Dependency:** Phase 2.

### 3a. `src/harness/persistence/repositories/types.py`

Add to `EvaluationAgentRegistrationCreateData`:
```python
score_scale_min: NotRequired[float | None]
score_scale_max: NotRequired[float | None]
```

Add to `EvaluationAgentRegistrationUpdateData` (already `total=False`):
```python
score_scale_min: float | None
score_scale_max: float | None
```

### 3b. `src/harness/persistence/repositories/evaluator_registration.py`

In `create()`, add after `declared_scoring_dimensions=...`:
```python
score_scale_min=data.get("score_scale_min"),
score_scale_max=data.get("score_scale_max"),
```

In `update()`, extend the `for field in (...)` tuple to include:
```python
"score_scale_min",
"score_scale_max",
```

### 3c. `src/harness/persistence/repositories/job.py`

In `set_evaluator_snapshot()`, add after `evaluator_declared_scoring_dimensions=...`:
```python
job.evaluator_score_scale_min = registration.score_scale_min
job.evaluator_score_scale_max = registration.score_scale_max
```

**Gate:** Create an `EvaluationAgentRegistration` with `score_scale_min=0.0,
score_scale_max=10.0`, fetch it back, verify both columns. Then `set_evaluator_snapshot`
on a draft `Job` copies both scale fields to `job.evaluator_score_scale_*`.

---

## Phase 4 — EvaluatorSnapshot + Pipeline

**Dependency:** Phase 3.

### 4a. `src/harness/evaluator/result.py`

Add two optional fields at the end of `EvaluatorSnapshot` (with defaults so existing
code that does not supply them continues to work):

```python
@dataclass(frozen=True)
class EvaluatorSnapshot:
    evaluation_agent_id: str
    endpoint_url: str
    auth_descriptor: dict
    timeout_seconds: int
    declared_scoring_dimensions: list[str]
    score_scale_min: float | None = None   # new
    score_scale_max: float | None = None   # new
```

### 4b. `src/harness/orchestrator/pipeline.py`

In `_evaluator_snapshot(job)`, add two lines at the end of the `EvaluatorSnapshot(...)`
call. Current code reads individual `job.evaluator_*` columns — follow the same pattern:

```python
return EvaluatorSnapshot(
    evaluation_agent_id=job.evaluation_agent_id,
    endpoint_url=job.evaluator_endpoint_url,
    auth_descriptor=job.evaluator_auth_descriptor,
    timeout_seconds=job.evaluator_timeout_seconds,
    declared_scoring_dimensions=job.evaluator_declared_scoring_dimensions or [],
    score_scale_min=job.evaluator_score_scale_min,    # new
    score_scale_max=job.evaluator_score_scale_max,    # new
)
```

**Gate:** `_evaluator_snapshot(job)` where `job.evaluator_score_scale_min = 0.0` returns
an `EvaluatorSnapshot` with `score_scale_min = 0.0`.

---

## Phase 5 — Form Validation (FR-001 to FR-007)

**Dependency:** None (parallelisable with Phases 1–4).

**File:** `src/harness/evaluator_registry/forms.py`

`parse_evaluator_form` returns `tuple[dict | None, dict[str, str]]`. The new scale
fields are added to the payload dict in the success branch; errors are added to the
errors dict in failure branches. No change to the return type.

### 5a. New helper `parse_scale_field`

Add after `duplicate_dimensions()`:

```python
def parse_scale_field(raw: str | None) -> tuple[float | None, str | None]:
    """Return (value, error). error is None on success; value is None when field is blank."""
    stripped = (raw or "").strip()
    if not stripped:
        return None, None
    try:
        return float(stripped), None
    except ValueError:
        return None, "Must be a numeric value (e.g. 0, 0.5, 10)."
```

### 5b. Update `parse_evaluator_form`

After parsing `declared_scoring_dimensions`, add in this order:

**FR-007 — numeric parse (always, regardless of dim count):**
```python
raw_scale_min = form.get("score_scale_min")
raw_scale_max = form.get("score_scale_max")
scale_min, err_min = parse_scale_field(raw_scale_min)
scale_max, err_max = parse_scale_field(raw_scale_max)
if err_min:
    errors["score_scale_min"] = err_min
if err_max:
    errors["score_scale_max"] = err_max
```

**FR-001 — dimension count cap:**
```python
if len(dimensions) > 10:
    errors["dimensions"] = (
        f"Maximum 10 dimensions allowed ({len(dimensions)} declared)."
    )
```

**FR-002 — duplicate blocking** (replace non-blocking warning):
```python
if "dimensions" not in errors:   # only if count check passed
    dups = duplicate_dimensions(dimensions)
    if dups:
        quoted = ", ".join(f"'{d}'" for d in dups)
        errors["dimensions"] = (
            f"Dimension names must be unique. Duplicate(s): {quoted}."
        )
```

**FR-005 — scale required when dims > 0:**
```python
if len(dimensions) > 0 and not errors.get("score_scale_min") and not errors.get("score_scale_max"):
    if scale_min is None or scale_max is None:
        msg = "Score minimum and maximum are required when dimensions are declared."
        if scale_min is None:
            errors["score_scale_min"] = msg
        if scale_max is None:
            errors["score_scale_max"] = msg
```

**FR-006 — `scale_min < scale_max`:**
```python
if (scale_min is not None and scale_max is not None
        and not errors.get("score_scale_min") and not errors.get("score_scale_max")):
    if scale_min >= scale_max:
        errors["score_scale_min"] = (
            "Score minimum must be strictly less than Score maximum."
        )
```

**Add to returned payload dict:**
```python
return {
    ...,   # all existing keys unchanged
    "score_scale_min": scale_min,
    "score_scale_max": scale_max,
}, {}
```

**Tests (9 new):**
- 11 dims → `errors["dimensions"]` with count
- Duplicate dims → `errors["dimensions"]` listing all duplicates
- 1 dim + empty scale → `errors["score_scale_min"]` and `errors["score_scale_max"]`
- 0 dims + empty scale → accepted (no error)
- `scale_min >= scale_max` → `errors["score_scale_min"]`
- Non-numeric scale field → `errors["score_scale_min"]`
- Valid scale → payload contains `score_scale_min=0.0, score_scale_max=10.0`
- Integer strings `"0"`, `"10"` → parsed as `0.0, 10.0`
- Zero as scale min `"0", "1"` → accepted (zero is a valid numeric bound)

---

## Phase 6 — Service Layer

**Dependency:** Phase 5 (form returns scale in payload); Phase 3 (repo accepts scale).

**File:** `src/harness/evaluator_registry/service.py`

`EvaluatorRegistryService.update()` builds its own `update_data` dict (currently lines
72–81) before calling `self._repo.update(...)`. New scale fields must be **explicitly
extracted** from `payload` and added to `update_data`:

```python
update_data: dict = {
    "display_name":                payload["display_name"],
    "description":                 payload.get("description"),
    "endpoint_url":                payload["endpoint_url"],
    "timeout_seconds":             payload["timeout_seconds"],
    "declared_scoring_dimensions": payload["declared_scoring_dimensions"],
    "supports_sse":                payload.get("supports_sse", False),
    "score_scale_min":             payload.get("score_scale_min"),   # new
    "score_scale_max":             payload.get("score_scale_max"),   # new
}
```

`create()` already delegates the full payload dict to `self._repo.create(payload)` — no
change needed in the service's `create()` method.

**Gate:** POST `/evaluators` (create) and PUT `/evaluators/{id}` (update) with a valid
scale round-trip through to the DB columns.

---

## Phase 7 — Registration Routes

**Dependency:** Phases 5–6.

**File:** `src/harness/ui/evaluator_registry/routes.py`

### 7a. Form parameters

In both `create_evaluator` and `update_evaluator` POST handlers, add:
```python
score_scale_min: str = Form(None),
score_scale_max: str = Form(None),
```
Include in the `form` dict passed to `parse_evaluator_form`:
```python
"score_scale_min": score_scale_min,
"score_scale_max": score_scale_max,
```

### 7b. `_reg_to_view` helper

Add to the returned dict:
```python
"score_scale_min": reg.score_scale_min,
"score_scale_max": reg.score_scale_max,
```

### 7c. New evaluator detail route (FR-018)

Add a GET route for read-only view. **Route ordering matters** — the literal `/evaluators/new`
GET must remain before `/evaluators/{evaluation_agent_id}` to avoid `"new"` matching
the ID pattern:

```python
@router.get("/evaluators/{evaluation_agent_id}", name="view_evaluator")
def view_evaluator(request: Request, evaluation_agent_id: str, ...):
    with get_session() as session:
        reg = EvaluatorRegistryService(session).get(evaluation_agent_id)
        if reg is None:
            raise HTTPException(status_code=404)
        reg_view = _reg_to_view(reg)
    return templates.TemplateResponse(
        request, "evaluator_registry/detail.html",
        {"reg": reg_view, **ctx(request)},
    )
```

Add a "View" link in `list.html` next to the existing "Edit" link.

---

## Phase 8 — Registration Form Template (FR-003, FR-004, client-side FR-007)

**Dependency:** Phase 7.

**File:** `src/harness/ui/evaluator_registry/templates/evaluator_registry/form.html`

### 8a. Dimension counter (FR-003)

Add `id="dimensions"` to the textarea and a `<span id="dim-counter">` below it:

```html
<textarea ... id="dimensions" name="dimensions" ...>...</textarea>
<div class="form-text mt-1">
  <span id="dim-counter">0 / 10 dimensions</span>
</div>
```

### 8b. Scale fields (FR-004)

Add a two-column row after the dimensions block (before `supports_sse`):

```html
<div class="row g-3 mb-4">
  <div class="col-6">
    <label class="form-label fw-semibold" for="score_scale_min">
      Score minimum
      <span class="text-muted fw-normal small">(required when dimensions declared)</span>
    </label>
    <input type="number" step="any"
           class="form-control {% if errors.score_scale_min %}is-invalid{% endif %}"
           id="score_scale_min" name="score_scale_min"
           value="{{ form.get('score_scale_min') if form.get('score_scale_min') is not none
                    else (reg.score_scale_min if reg and reg.score_scale_min is not none else '') }}"
           placeholder="e.g. 0">
    {% if errors.score_scale_min %}<div class="invalid-feedback">{{ errors.score_scale_min }}</div>{% endif %}
  </div>
  <div class="col-6">
    <label class="form-label fw-semibold" for="score_scale_max">Score maximum</label>
    <input type="number" step="any"
           class="form-control {% if errors.score_scale_max %}is-invalid{% endif %}"
           id="score_scale_max" name="score_scale_max"
           value="{{ form.get('score_scale_max') if form.get('score_scale_max') is not none
                    else (reg.score_scale_max if reg and reg.score_scale_max is not none else '') }}"
           placeholder="e.g. 1">
    {% if errors.score_scale_max %}<div class="invalid-feedback">{{ errors.score_scale_max }}</div>{% endif %}
  </div>
</div>
```

### 8c. Live counter JS (FR-003)

In `{% block scripts %}`, after the existing JS:

```javascript
function updateDimCounter() {
  var lines = document.getElementById('dimensions').value
      .split('\n').filter(function(l) { return l.trim() !== ''; });
  var span = document.getElementById('dim-counter');
  span.textContent = lines.length + ' / 10 dimensions';
  span.style.fontWeight = lines.length >= 10 ? 'bold' : 'normal';
  span.style.color = lines.length >= 10 ? 'var(--bs-danger)' : '';
}
document.getElementById('dimensions').addEventListener('input', updateDimCounter);
updateDimCounter();   // initialise on page load (edit form pre-population)
```

---

## Phase 9 — Evaluator Detail Template (FR-018)

**Dependency:** Phase 7c.

**File (new):** `src/harness/ui/evaluator_registry/templates/evaluator_registry/detail.html`

Key element — the scale row:
```html
<dt>Score scale</dt>
<dd>
  {% if reg.score_scale_min is not none and reg.score_scale_max is not none %}
    {{ reg.score_scale_min }} – {{ reg.score_scale_max }}
  {% else %}
    <span class="text-muted">Scale: not declared</span>
  {% endif %}
</dd>
```

---

## Phase 10 — Response-Time Range Validation (FR-010 to FR-014)

**Dependency:** Phase 4 (`EvaluatorSnapshot` has scale fields).

### 10a. `src/harness/evaluator/validation.py`

New function after `compute_harness_annotations`:

```python
def validate_score_ranges(
    scores: list,
    scale_min: float | None,
    scale_max: float | None,
) -> list[str]:
    """
    Returns out-of-range problem strings (empty list = all ok).

    FR-014: null scale → skip entirely.
    FR-013: null value or absent key → skip. Integer/float 0 is validated normally.
    FR-012: string score → skip.
    FR-010: numeric (int/float, bool excluded) → check inclusive bounds.
    FR-011: all violations collected before returning.
    """
    if scale_min is None or scale_max is None:          # FR-014
        return []
    problems: list[str] = []
    for entry in scores or []:
        if not isinstance(entry, dict):
            continue
        if "score" not in entry:                        # FR-013 absent key
            continue
        score = entry["score"]
        if score is None:                               # FR-013 null value
            continue
        if isinstance(score, bool):                     # excluded by structural rules
            continue
        if isinstance(score, str):                      # FR-012 string bypass
            continue
        if isinstance(score, (int, float)):
            if not (scale_min <= score <= scale_max):   # FR-010 inclusive
                name = entry.get("parameter_name", "?")
                problems.append(
                    f"score {score} for dimension '{name}' is outside the "
                    f"declared scale [{scale_min}, {scale_max}]"
                )
    return problems
```

### 10b. `src/harness/evaluator/client.py`

Import `validate_score_ranges`. After the existing `if problems:` block (line 111),
before `compute_harness_annotations`:

```python
range_problems = validate_score_ranges(
    body.get("evaluationScores", []),
    snapshot.score_scale_min,
    snapshot.score_scale_max,
)
if range_problems:
    return EvaluatorResult(
        ok=False,
        error_stage="evaluator_result",
        error_details="; ".join(range_problems),
        status_code=response.status_code,
    )
```

**Tests (8 new in `tests/unit/evaluator/test_validation.py`):**
- In-range score → empty list
- Out-of-range score → problem string with dim name and value
- Integer zero score within `[0, 1]` → no problem (zero is validated, not bypassed)
- Integer zero score outside `[0.5, 1]` → problem (zero is not treated as absent)
- String score → empty list (FR-012)
- Absent `score` key → empty list (FR-013)
- `null` score value → empty list (FR-013)
- `scale_min=None` → empty list (FR-014)
- Two out-of-range dims → both problems listed (FR-011)

---

## Phase 11 — Analytics (FR-015, FR-016, FR-017)

**Dependency:** Phase 3 (job has scale columns); Phase 10 (no dependency, can overlap).

### 11a. Fix `ScoreEntry` — add `is_numeric_score`

**File:** `src/harness/ui/detail/analytics.py`

Add `is_numeric_score: bool = True` at the end of `ScoreEntry` (with default, so no
existing construction calls break):

```python
@dataclass(frozen=True)
class ScoreEntry:
    parameter_name: str
    score: float
    reasoning: str
    verdict: str | None
    overall_verdict: str | None
    error: bool
    unit_id: str | None = None
    utterance_intent: str | None = None
    is_numeric_score: bool = True    # new — False for string/null originals
```

### 11b. Fix `score_entries_from_utterances` — both callers

**The falsy-zero bug exists in two files. Fix both.**

**File 1:** `src/harness/ui/detail/view.py:383`
**File 2:** `src/harness/ui/chat_session/view.py:138`

Replace `score=float(s.get("score") or 0.0)` with explicit type detection:

```python
raw_score = s.get("score")   # or p.get("score") in the chat variant
if isinstance(raw_score, bool):
    # booleans: excluded by structural validation; treat as non-numeric
    numeric_val = 0.0
    is_numeric = False
elif isinstance(raw_score, (int, float)):
    numeric_val = float(raw_score)   # includes 0 — valid numeric, IS validated
    is_numeric = True
elif isinstance(raw_score, str):
    try:
        numeric_val = float(raw_score)
    except (ValueError, TypeError):
        numeric_val = 0.0
    is_numeric = False               # string origin → excluded from normalised mean
else:
    # None or missing
    numeric_val = 0.0
    is_numeric = False
```

Construct `ScoreEntry` with `score=numeric_val, is_numeric_score=is_numeric`.

### 11c. `compute_analytics` — add scale keyword args (Option A for chat compatibility)

**File:** `src/harness/ui/detail/analytics.py`

Change the signature to:
```python
def compute_analytics(
    entries: list[ScoreEntry],
    declared_dims: list[str],
    *,
    score_scale_min: float | None = None,
    score_scale_max: float | None = None,
) -> RunAnalytics:
```

The keyword-only `None` defaults mean the existing chat session call site
(`chat_session/routes.py:815`) requires **no change** — it continues to pass only
`entries` and `declared_dims`, which resolves to the legacy path (FR-017).

### 11d. `_normalise_to_declared` helper

Add a new private helper in `analytics.py`:

```python
def _normalise_to_declared(
    scores: list[float], scale_min: float, scale_max: float
) -> list[float]:
    rng = scale_max - scale_min
    if rng == 0:
        return [0.5] * len(scores)
    return [(x - scale_min) / rng for x in scores]
```

### 11e. Per-parameter histogram — declared scale bounds (FR-016)

In the per-parameter stats loop, choose normalisation based on whether scale is declared:

```python
if score_scale_min is not None and score_scale_max is not None:
    # FR-016: declared bounds as axis
    normalised = _normalise_to_declared(scores, score_scale_min, score_scale_max)
    hist_raw_min, hist_raw_max = score_scale_min, score_scale_max
else:
    # FR-017: legacy — run distribution bounds
    normalised = _normalise(scores)
    hist_raw_min, hist_raw_max = mn, mx
histogram = _build_histogram(normalised, hist_raw_min, hist_raw_max, mean, stddev)
```

### 11f. `overall_mean_score` — normalised when scale declared (FR-015)

Replace the current raw mean line:

```python
if score_scale_min is not None and score_scale_max is not None:
    scale_rng = score_scale_max - scale_min
    numeric_only = [e for e in valid if e.is_numeric_score]
    if numeric_only and scale_rng != 0:
        overall_mean_score = statistics.mean(
            [(e.score - score_scale_min) / scale_rng for e in numeric_only]
        )
    else:
        overall_mean_score = None   # all-string or all-null jobs → None (FR-015)
else:
    # FR-017: raw arithmetic mean (unchanged for legacy jobs)
    overall_mean_score = (
        sum(e.score for e in valid) / len(valid) if valid else None
    )
```

### 11g. `_analytics_context` and its two call sites — `detail/routes.py`

Update `_analytics_context` signature:

```python
def _analytics_context(
    utterances: list,
    dims: list[str],
    total_count: int | None = None,
    *,
    score_scale_min: float | None = None,
    score_scale_max: float | None = None,
) -> dict:
    ...
    return {
        "analytics": compute_analytics(
            entries, dims,
            score_scale_min=score_scale_min,
            score_scale_max=score_scale_max,
        ),
        ...
    }
```

**Two call sites in `detail/routes.py` — both must be updated:**

`job_detail` (line 183):
```python
analytics_ctx = _analytics_context(
    utterances, dims, job.total_utterance_count,
    score_scale_min=job.evaluator_score_scale_min,
    score_scale_max=job.evaluator_score_scale_max,
)
```

`_rerender_error` (line 401) — `job` is already fetched at line 395 in this function:
```python
analytics_ctx = _analytics_context(
    utterances, dims,
    score_scale_min=job.evaluator_score_scale_min,
    score_scale_max=job.evaluator_score_scale_max,
)
```

**Tests (4 new in `tests/unit/detail/test_analytics.py`):**
- Scale `[0, 10]`, scores `[5.0, 7.0]` → `overall_mean_score = 0.6`
- All `is_numeric_score=False` entries → `overall_mean_score = None`
- Declared scale histogram: score at 50% of range lands in bucket 4 or 5
- Legacy (no scale): raw mean unchanged, run-distribution histogram

---

## Phase 12 — Dynamic Labels and Export Updates (FR-019, FR-020, FR-022)

**Dependency:** Phase 3 (job has scale columns).

**File:** `src/harness/ui/detail/view.py`

### 12a. `_score_label` helper

Add after `_HEADER_MAP`:

```python
def _score_label(scale_min: float | None, scale_max: float | None) -> str:
    """FR-022: dynamic label from job snapshot; legacy jobs keep 'Score (0–1)'."""
    if scale_min is not None and scale_max is not None:
        return f"Score ({scale_min}–{scale_max})"
    return "Score (0–1)"
```

### 12b. `_flat_header` — accept scale kwargs

```python
def _flat_header(
    dim_names: list[str],
    max_sources: int,
    scale_min: float | None = None,
    scale_max: float | None = None,
) -> list[str]:
    label = _score_label(scale_min, scale_max)
    # Replace the hardcoded ": Score (0–1)" suffix on *_score columns:
    ...
```

### 12c. `results_flat_csv_builder` and `results_flat_xlsx_builder`

Pass scale from job:
```python
header = _flat_header(
    dim_names, max_sources,
    job.evaluator_score_scale_min,
    job.evaluator_score_scale_max,
)
```

### 12d. Long-format builders (`results_csv_builder`, `results_xlsx_builder`)

Replace the static `_HEADER_MAP["score"]` lookup in the header row with:
```python
score_col_label = _score_label(job.evaluator_score_scale_min, job.evaluator_score_scale_max)
```
Use `score_col_label` in the header list instead of the mapped string.

### 12e. Data dictionary (FR-019)

New helper:
```python
def _score_dict_description(scale_min: float | None, scale_max: float | None) -> str:
    if scale_min is not None and scale_max is not None:
        return (
            f"Numeric score on the declared scale [{scale_min} (minimum) — "
            f"{scale_max} (maximum)]. Values are reported as received from the "
            "evaluator (not normalised). This spec assumes higher score = better performance."
        )
    return "Numeric score (scale undeclared; values reported as received from the evaluator)"
```

Pass `_score_dict_description(job.evaluator_score_scale_min, job.evaluator_score_scale_max)`
to the data dictionary writer functions. Replace the hardcoded score row text with this
dynamic value.

**Tests:**
- Flat CSV with scale `[0, 10]` → header `"accuracy: Score (0–10)"`
- Flat CSV with no scale → header `"accuracy: Score (0–1)"`
- XLSX data dictionary score row describes declared scale bounds

---

## Phase 13 — Detail View Score Column Header (FR-022)

**Dependency:** Phase 12 (`_score_label` exists); Phase 3 (job has scale columns).

**File:** `src/harness/ui/detail/routes.py`

In `job_detail`, add to template context:
```python
from harness.ui.detail.view import _score_label
...
"score_label": _score_label(job.evaluator_score_scale_min, job.evaluator_score_scale_max),
```

Also add to `_rerender_error` context (same pattern — `job` is in scope at line 395).

**File:** `src/harness/ui/detail/templates/detail/index.html`

Replace the hardcoded `<th>Scores</th>` (or equivalent) with:
```html
<th>{{ score_label }}</th>
```

**Gate:** Job with scale `[0, 10]` → `<th>Score (0–10)</th>`. Legacy job → `<th>Score (0–1)</th>`.

---

## Phase 14 — Test Coverage

| File | Tests |
|---|---|
| `tests/unit/evaluator_registry/test_forms.py` | 9 new tests (Phase 5) |
| `tests/unit/evaluator/test_validation.py` | 9 new tests (Phase 10) |
| `tests/unit/detail/test_analytics.py` | 4 new tests (Phase 11) |
| `tests/unit/persistence/test_repositories/test_evaluator_registration_repository.py` | create with scale, update scale, create without scale → null |
| `tests/unit/persistence/test_repositories/test_job_repository.py` | `set_evaluator_snapshot` copies scale columns |
| `tests/unit/export/test_builder.py` | Dynamic column headers (flat + long); data dict description |
| `tests/integration/test_evaluator_registry_ui.py` | 11 dims, duplicate dims, missing scale, min≥max, valid round-trip, legacy zero-dim edit |
| `tests/integration/test_orchestrator_e2e.py` | Out-of-range score fails row; legacy null scale passes; per-row isolation |

### Regression checks

- `tests/integration/test_detail_ui.py` — existing tests must pass unchanged (analytics
  signature change is backward-compatible via `None` defaults)
- Chat session analytics: `chat_session/routes.py` call to `compute_analytics` requires
  **no change** — the new keyword args default to `None`, triggering the FR-017 legacy path

---

## Per-Phase Acceptance Gates

| Phase | Gate |
|---|---|
| 1 | `alembic upgrade head` OK; both tables have scale columns |
| 2 | ORM attribute reads return `None` on existing rows; no SA warning |
| 3 | `create` + `update` persist scale; `set_evaluator_snapshot` copies to job |
| 4 | `_evaluator_snapshot(job)` propagates scale to `EvaluatorSnapshot` |
| 5 | All 9 forms tests pass; existing 14 forms tests unchanged |
| 6 | Scale round-trips through service `update()` to DB |
| 7 | POST `/evaluators` with scale → 302; GET `/evaluators/{id}` → 200 |
| 8 | Counter shows "11 / 10 dimensions" in red at 11 lines; scale fields pre-populate on edit |
| 9 | GET `/evaluators/{id}` shows `"0.0 – 10.0"` or `"Scale: not declared"` |
| 10 | Out-of-range → `error_stage="evaluator_result"` with dim name; integer zero validated |
| 11 | Normalised mean = 0.6 for scores [5, 7] on scale [0, 10]; histogram uses declared bounds |
| 12 | Flat CSV header reads `"accuracy: Score (0–10)"` for declared-scale job |
| 13 | Results table `<th>` is `"Score (0–10)"` for declared-scale job; `"Score (0–1)"` for legacy |
| 14 | All new tests pass; no regressions in chat session or detail UI tests |
