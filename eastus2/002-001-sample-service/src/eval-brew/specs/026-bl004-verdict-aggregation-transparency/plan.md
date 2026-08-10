# BL-004 Implementation Plan — Verdict Aggregation Transparency

**Spec:** `docs/backlog/BL-004-verdict-aggregation-transparency.md`
**Created:** 2026-08-10

---

## Architecture Notes

### How verdict rollup actually works

The harness does NOT compute the overall verdict itself. The evaluator service
returns `evaluationVerdict` as part of its response, and the harness stores and
displays it verbatim. The worst-case rollup rule (fail > warn > pass) is a
**convention** followed by evaluators — documented in the UI reading guide but
never enforced by the harness.

Per-dimension verdicts are returned in `evaluationScores[*].verdict` and stored
in `evaluation_result.evaluation_scores` as a JSON column. They are available
through `row_view()` → `scores_cells`, each cell having `name`, `score`, `verdict`.

### Where the data lives

- Rollup documentation: already in `index.html` lines 215–219 and 308; tooltip
  text in `routes.py` TOOLTIP_COPY dict; data dictionary has minimal "Worst-case"
  text only.
- `scoring_thresholds`: new JSON column on `evaluation_agent_registration` and
  `job` (snapshotted like scale fields).
- Template context: `job_detail` and `_rerender_error` in `detail/routes.py`
  must pass `scoring_thresholds` dict to the template.

### Threshold format (stored as JSON)

```json
{
  "relevance":    {"pass": 0.80, "warn": 0.60},
  "grounding":    {"pass": 0.75, "warn": 0.50},
  "completeness": {"pass": 0.70, "warn": 0.50}
}
```

Semantics: score ≥ `pass` → pass; score ≥ `warn` → warn; score < `warn` → fail.
`pass` must be strictly greater than `warn`. Thresholds apply within the declared
score scale (not normalised to 0–1 before comparison).

---

## Dependency Order

```
Phase 1 (Data dictionary + verdict tooltip — no DB change)
Phase 2 (Migration 0011)
   └─ Phase 3 (ORM + repos + service)
         └─ Phase 4 (Form parsing + routes + templates)
         └─ Phase 5 (Detail view wiring)
               └─ Phase 6 (Export data dictionary)
Phase 7 (Tests — written after each phase or as a sweep)
```

---

## Phase 1 — Data Dictionary Rollup Documentation (no DB change)

**Files:**
- `src/harness/ui/detail/view.py` — update `_DICT_S1`, `_FLAT_DICT_FIXED`,
  `_DICT_VERDICTS`
- `src/harness/ui/detail/templates/detail/index.html` — tooltip on `<th>Verdict</th>`

### 1a. `_DICT_S1` update

Current "Overall Result" row (line 521):
```python
("Overall Result", "Text", "Worst-case verdict for this utterance", "pass / warn / fail / blank"),
```

Replace with:
```python
("Overall Result", "Text",
 "Worst-case verdict across all evaluated dimensions. "
 "Rule: fail if any dimension fails; warn if any warns and none fails; "
 "pass only if every dimension passes. Determined by the evaluator service.",
 "pass / warn / fail / blank"),
```

### 1b. `_FLAT_DICT_FIXED` update

Current "Overall Result" row (line 749):
```python
("Overall Result", "Text", "Worst-case verdict across all dimensions (pass / warn / fail)"),
```

Replace with:
```python
("Overall Result", "Text",
 "Worst-case verdict across all evaluated dimensions — "
 "fail if any dimension fails; warn if any warns; pass only if every dimension passes."),
```

### 1c. `_DICT_VERDICTS` update

Improve the explanations to reference the rollup:
```python
_DICT_VERDICTS = [
    ("Verdict value", "Meaning"),
    ("pass", "All dimension scores meet or exceed the evaluator's configured pass threshold"),
    ("warn",
     "At least one dimension score is below the pass threshold but above the warn threshold — "
     "review recommended"),
    ("fail",
     "At least one dimension score is below the warn threshold — action required. "
     "A single failing dimension causes the overall result to be fail."),
    ("(blank)", "Utterance errored before evaluation; no score was produced"),
]
```

### 1d. Verdict column header tooltip in `index.html`

Replace line 572:
```html
<th>{{ sortlink('verdict', 'Verdict') }}</th>
```
with:
```html
<th title="Worst-case across all dimensions: fail if any dimension fails; warn if any warns; pass only if every dimension passes.">
  {{ sortlink('verdict', 'Verdict') }}
</th>
```

---

## Phase 2 — Database Migration

**File (new):** `src/harness/persistence/migrations/versions/0011_add_scoring_thresholds.py`

```python
revision: str = "0011"
down_revision: str | None = "0010"
```

Two tables, two columns:

`evaluation_agent_registration`:
- `scoring_thresholds` — `JSON`, nullable

`job`:
- `evaluator_scoring_thresholds` — `JSON`, nullable

Follow idempotent inspect-before-add pattern from 0010.

---

## Phase 3 — ORM Models + Repositories + Service

### 3a. `src/harness/persistence/models/evaluator_registration.py`

Add after `score_scale_max`:
```python
scoring_thresholds: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

### 3b. `src/harness/persistence/models/job.py`

Add after `evaluator_score_scale_max`:
```python
evaluator_scoring_thresholds: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

### 3c. `src/harness/persistence/repositories/types.py`

Add to `EvaluatorRegistrationData` TypedDict:
```python
scoring_thresholds: dict | None
```

Add to `JobData` TypedDict:
```python
evaluator_scoring_thresholds: dict | None
```

### 3d. `src/harness/persistence/repositories/evaluator_registration.py`

In `create()` and `update()` — include `scoring_thresholds` in column list.

### 3e. `src/harness/persistence/repositories/job.py`

In `set_evaluator_snapshot()` — add:
```python
job.evaluator_scoring_thresholds = reg.scoring_thresholds
```

### 3f. `src/harness/evaluator_registry/service.py`

In `update()` — add to `update_data`:
```python
"scoring_thresholds": payload.get("scoring_thresholds"),
```

---

## Phase 4 — Form Parsing + Registration Routes + Templates

### 4a. `src/harness/evaluator_registry/forms.py`

New helper `parse_thresholds_field`:
```python
def parse_thresholds_field(raw: str | None) -> tuple[dict | None, str | None]:
    """Parse and validate JSON threshold declaration.

    Returns (thresholds_dict, error_message). error is None on success.
    Returns (None, None) when field is blank (thresholds are optional).
    """
    stripped = (raw or "").strip()
    if not stripped:
        return None, None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "Must be a JSON object mapping dimension names to {\"pass\": N, \"warn\": N}."
    for dim, bounds in data.items():
        if not isinstance(bounds, dict):
            return None, f"Threshold for '{dim}' must be an object with 'pass' and 'warn' keys."
        for key in ("pass", "warn"):
            if key not in bounds:
                return None, f"Threshold for '{dim}' is missing the '{key}' key."
            val = bounds[key]
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                return None, f"Threshold '{key}' for '{dim}' must be a number."
        if bounds["pass"] <= bounds["warn"]:
            return None, (
                f"'pass' threshold ({bounds['pass']}) for '{dim}' must be strictly "
                f"greater than 'warn' threshold ({bounds['warn']})."
            )
    return data, None
```

Add to `parse_evaluator_form` after scale parsing:
```python
raw_thresholds = form.get("scoring_thresholds_json")
thresholds, err_thresholds = parse_thresholds_field(raw_thresholds)
if err_thresholds:
    errors["scoring_thresholds"] = err_thresholds
```

Add to payload dict:
```python
"scoring_thresholds": thresholds,
```

### 4b. `src/harness/ui/evaluator_registry/routes.py`

In `create_evaluator` and `update_evaluator` POST handlers, add:
```python
scoring_thresholds_json: str = Form(None),
```
Include in `form` dict:
```python
"scoring_thresholds_json": scoring_thresholds_json,
```

In `_reg_to_view`:
```python
"scoring_thresholds": reg.scoring_thresholds,
"scoring_thresholds_json": (
    json.dumps(reg.scoring_thresholds, indent=2) if reg.scoring_thresholds else ""
),
```

### 4c. `src/harness/ui/evaluator_registry/templates/evaluator_registry/form.html`

Add textarea after the scale fields block:
```html
<div class="mb-4">
  <label class="form-label fw-semibold" for="scoring_thresholds_json">
    Scoring thresholds
    <span class="text-muted fw-normal small">(optional JSON)</span>
  </label>
  <textarea class="form-control font-monospace {% if errors.scoring_thresholds %}is-invalid{% endif %}"
            id="scoring_thresholds_json" name="scoring_thresholds_json" rows="5"
            placeholder='{&#10;  "accuracy": {"pass": 0.80, "warn": 0.60},&#10;  "fluency":  {"pass": 0.75, "warn": 0.50}&#10;}'>{{ form.get('scoring_thresholds_json') or (reg.scoring_thresholds_json if reg else '') }}</textarea>
  {% if errors.scoring_thresholds %}<div class="invalid-feedback">{{ errors.scoring_thresholds }}</div>{% endif %}
  <div class="form-text">
    One entry per declared dimension. <code>"pass"</code> must be strictly greater than
    <code>"warn"</code>. Scores ≥ pass → pass; ≥ warn → warn; below warn → fail.
  </div>
</div>
```

### 4d. `src/harness/ui/evaluator_registry/templates/evaluator_registry/detail.html`

Add "Scoring thresholds" section after "Score scale":
```html
<dt class="col-sm-4">Scoring thresholds</dt>
<dd class="col-sm-8">
  {% if reg.scoring_thresholds %}
    <table class="table table-sm table-bordered mb-0 small">
      <thead class="table-light">
        <tr><th>Dimension</th><th>Pass ≥</th><th>Warn ≥</th><th>Fail &lt;</th></tr>
      </thead>
      <tbody>
      {% for dim, t in reg.scoring_thresholds.items() %}
        <tr>
          <td>{{ dim }}</td>
          <td class="text-success">{{ t.pass }}</td>
          <td class="text-warning">{{ t.warn }}</td>
          <td class="text-danger">{{ t.warn }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% else %}
    <span class="text-muted">Thresholds not declared by evaluator</span>
  {% endif %}
</dd>
```

---

## Phase 5 — Detail View: Threshold Indicators + Context Wiring

### 5a. `src/harness/ui/detail/routes.py`

In `job_detail` and `_rerender_error`, add to template context:
```python
"scoring_thresholds": job.evaluator_scoring_thresholds,
```

### 5b. `src/harness/ui/detail/templates/detail/index.html`

**Verdict column header tooltip (Phase 1d already covers this).**

**Per-dimension threshold indicator in scores_cells loop (lines 590–594):**

```html
{% for c in r.scores_cells %}
  <li{% if c.get('unexpected') %} class="unexpected"{% endif %}>
    {{ c.name }}: {{ c.score }}
    {% if c.get('verdict') %} <span class="text-muted">[{{ c.verdict }}]</span>{% endif %}
    {% if scoring_thresholds and scoring_thresholds.get(c.name) %}
      {% set t = scoring_thresholds[c.name] %}
      <span class="text-muted ms-1 small" style="font-size:.7rem"
            title="pass ≥ {{ t.pass }}; warn ≥ {{ t.warn }}; fail &lt; {{ t.warn }}">ⓘ</span>
    {% endif %}
  </li>
{% endfor %}
```

The `ⓘ` with title attribute gives a browser tooltip on hover without cluttering
the display. The threshold values are not rendered inline to keep the score cell
compact.

---

## Phase 6 — Export Data Dictionary: Rollup Rule + Threshold Rows

### 6a. `_write_data_dictionary` signature + rollup section

Update signature:
```python
def _write_data_dictionary(ws, scale_min=None, scale_max=None, scoring_thresholds=None) -> None:
```

After the existing "Verdict Value Definitions" section, add:

```python
ws.append([])
_section("Rollup Rule")
ws.append([])
ws.append(["The harness overall verdict follows a worst-case convention:"])
ws.append(["  fail   — if any evaluated dimension returns 'fail'"])
ws.append(["  warn   — if any evaluated dimension returns 'warn' and none returns 'fail'"])
ws.append(["  pass   — only when every evaluated dimension returns 'pass'"])
ws.append(["Evaluators determine per-dimension verdicts using their own threshold configuration."])

if scoring_thresholds:
    ws.append([])
    _section("Threshold Declarations (as configured at job time)")
    ws.append([])
    _write_header_row(ws, ("Dimension", "Pass threshold (≥)", "Warn threshold (≥)", "Fail threshold (<)"), fill=True)
    for dim, t in scoring_thresholds.items():
        ws.append([dim, t.get("pass"), t.get("warn"), t.get("warn")])
```

Update callers in `results_xlsx_builder`:
```python
_write_data_dictionary(
    ws3,
    job.evaluator_score_scale_min,
    job.evaluator_score_scale_max,
    job.evaluator_scoring_thresholds,
)
```

### 6b. Flat XLSX builder — same rollup section

After the sources section in `results_flat_xlsx_builder`, add the same rollup
section and conditional threshold section (using `job.evaluator_scoring_thresholds`).

---

## Phase 7 — Tests

### `tests/unit/evaluator_registry/test_forms.py` (new tests)

- `test_thresholds_valid_json_parsed` — valid JSON → thresholds dict in payload
- `test_thresholds_invalid_json_error` — non-JSON → `errors["scoring_thresholds"]`
- `test_thresholds_pass_must_exceed_warn` — pass ≤ warn → error
- `test_thresholds_blank_is_none` — empty string → `thresholds=None`, no error
- `test_thresholds_missing_warn_key` — missing key → error

### `tests/unit/detail/test_view.py` (new tests)

- `test_xlsx_data_dict_rollup_rule_section_present` — "Rollup Rule" text in data dict
- `test_xlsx_data_dict_threshold_section_present` — when thresholds → dimension row
- `test_xlsx_data_dict_no_threshold_section_when_none` — when no thresholds → no dim row
- `test_flat_xlsx_data_dict_rollup_rule_present` — rollup rule in flat XLSX dict

---

## Per-Phase Acceptance Gates

| Phase | Gate |
|---|---|
| 1 | Data dict "Overall Result" cell contains "warn if any warns"; tooltip on Verdict th |
| 2 | `alembic upgrade head` OK; both tables have new nullable JSON columns |
| 3 | `set_evaluator_snapshot` copies scoring_thresholds to job |
| 4 | POST `/evaluators` with threshold JSON → 302; GET shows threshold table |
| 5 | Job with thresholds → ⓘ tooltip visible on each declared-dim score cell |
| 6 | XLSX data dict has Rollup Rule section; threshold rows when declared |
| 7 | All new tests pass; no regressions |
