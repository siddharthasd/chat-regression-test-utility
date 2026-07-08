# Data Model: Live Chat Session Analytics (019)

**Generated**: 2026-07-08 | **Plan**: [plan.md](plan.md)

---

## Overview

Feature 019 introduces no new database tables and requires no Alembic migration. All analytics are computed at page-load time from existing `chat_session`, `chat_turn`, and `chat_turn_result` table data. The data model for this feature is:

1. **Shared engine types** imported from `harness.ui.detail.analytics` (018): `ScoreEntry`, `RunAnalytics`, `ParameterStats`, etc. — no redefinition.
2. **New view functions** added to `harness.ui.chat_session.view`: `score_entries_from_turns()`, `turn_explorer_view()`, `results_csv_builder()`, `results_json_builder()`.
3. **Template context** passed by the new route handler to `analytics.html`.

---

## Shared Engine Types (imported from 018)

No modifications. Imported directly from `harness.ui.detail.analytics`:

```python
from harness.ui.detail.analytics import (
    ScoreEntry,
    VerdictCount,
    HistogramBucket,
    ParameterStats,
    RunAnalytics,
    compute_analytics,
)
```

See `specs/018-job-run-analytics-dashboard/data-model.md` for the full definitions.

---

## ScoreEntry Mapping — Live Chat → Engine Input

One `ScoreEntry` is created per turn per parameter. The mapping from 019 ORM to `ScoreEntry`:

| `ScoreEntry` field | Source |
|---|---|
| `parameter_name` | `ChatTurnResult.final_evaluation_result["parameters"][n]["parameter_name"]` |
| `score` | `ChatTurnResult.final_evaluation_result["parameters"][n]["score"]` as `float` |
| `reasoning` | `ChatTurnResult.final_evaluation_result["parameters"][n]["reasoning"]` or `""` |
| `verdict` | `ChatTurnResult.final_evaluation_result["parameters"][n].get("verdict")` — `None` when absent (v1) |
| `overall_verdict` | `ChatTurnResult.final_evaluation_result.get("overallVerdict")` |
| `error` | `ChatTurn.status == "failed"` |

**Edge cases**:
- `final_evaluation_result` is `None` (turn failed before evaluation reached JSON stage): produce a single error `ScoreEntry` with `parameter_name=""`, `score=0.0`, `error=True`.
- `parameters` list is empty: no `ScoreEntry` rows produced for that turn; turn contributes only to `error_count`.
- `score` value not a float: `float(score)` with fallback `0.0`.

---

## View Layer Additions (`chat_session/view.py`)

### score_entries_from_turns

```python
def score_entries_from_turns(turns: list[ChatTurn]) -> list[ScoreEntry]:
    """
    Map ChatTurn list (with result relationship loaded) to ScoreEntry list
    for the RunAnalytics engine. Turns with status 'in_progress' are excluded.
    """
    entries = []
    for turn in turns:
        if turn.status == "in_progress":
            continue
        is_error = turn.status == "failed"
        result = turn.result  # ChatTurnResult | None
        result_json = (result.final_evaluation_result or {}) if result else {}
        params = result_json.get("parameters", [])
        overall_verdict = result_json.get("overallVerdict")

        for p in params:
            if not isinstance(p, dict):
                continue
            entries.append(ScoreEntry(
                parameter_name=p.get("parameter_name", ""),
                score=float(p.get("score", 0.0)),
                reasoning=p.get("reasoning") or "",
                verdict=p.get("verdict"),          # None for v1
                overall_verdict=overall_verdict,
                error=is_error,
            ))

        if is_error and not params:
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

### turn_explorer_view

```python
def turn_explorer_view(turns: list[ChatTurn]) -> list[dict]:
    """
    Produce the Turn Explorer row representation for the template.
    Excludes in-progress turns. Ordered by turn index ascending (caller's order).
    """
```

Returns a list of dicts keyed: `turn_index`, `user_message`, `assembled_response`, `overall_verdict`, `scores`, `error_stage`, `error_details`, `status`, `result_json_str`.

- `scores`: list of `{"name": str, "score": float | None, "reasoning": str, "verdict": str | None}` — one entry per parameter.
- `result_json_str`: JSON string of the full `final_evaluation_result` for copy-to-clipboard in row expand.
- Truncation (200 chars) is applied at the template level, not in this function.

### results_csv_builder

```python
def results_csv_builder(
    session: ChatSession,
    turns: list[ChatTurn],
) -> tuple[str, str]:
    """
    Build long-format results CSV. Returns (filename, csv_body).
    Excludes in-progress turns.
    """
```

**Filename derivation**:
```python
raw_name = session.session_name or ""
sanitised = _sanitise_session_name(raw_name)
if not sanitised:
    sanitised = f"session-{session.chat_session_id[:8]}"
filename = f"{sanitised}-results.csv"
```

**CSV schema** (header row always present):
```
turnIndex,userMessage,assembledResponse,overallVerdict,parameterName,score,verdict,reasoning
```

Row rules:
- One row per turn-parameter pair.
- Failed turns: one row with `overallVerdict` = error stage description, `parameterName` / `score` / `verdict` / `reasoning` all empty.
- `verdict` column: empty string when absent (v1 entries).
- Ordering: by `turn.turn_index` ASC, then by declared-dimension order within each turn.

### results_json_builder

```python
def results_json_builder(
    session: ChatSession,
    turns: list[ChatTurn],
) -> tuple[str, str]:
    """
    Build nested-by-turn results JSON. Returns (filename, json_body).
    Excludes in-progress turns.
    """
```

**Filename**: same `_sanitise_session_name` logic as CSV builder, `.json` extension.

**JSON schema**:
```json
[
  {
    "turnIndex": 1,
    "userMessage": "string",
    "assembledResponse": "string | null",
    "overallVerdict": "string | null",
    "errorStatus": "string | null",
    "errorStage": "string | null",
    "parameters": [
      {
        "parameter_name": "string",
        "score": 0.91,
        "reasoning": "string"
      }
    ]
  }
]
```

- `verdict` key inside parameter objects: **omitted** (not `null`) when the stored entry has no `verdict` field (v1 contract).
- `parameters` array: empty `[]` for failed turns.
- Ordering: by `turn.turn_index` ASC.

### _sanitise_session_name (private helper)

```python
import re

def _sanitise_session_name(name: str) -> str | None:
    name = name.lower().strip()
    name = name.replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or None
```

---

## Repository Addition (`chat_session_repository.py`)

### get_turns_with_results

```python
def get_turns_with_results(self, session_id: str) -> list[ChatTurn]:
    """
    Return all completed and failed turns for a session, ordered by created_at ASC,
    with the 'result' relationship selectin-loaded. Excludes in-progress turns.
    """
    return (
        self.db.query(ChatTurn)
        .options(selectinload(ChatTurn.result))
        .filter(
            ChatTurn.session_id == session_id,
            ChatTurn.status.in_(["completed", "failed"]),
        )
        .order_by(ChatTurn.created_at.asc())
        .all()
    )
```

This method has no `LIMIT` clause. It is called exclusively by the analytics route handler.

---

## Template Context

The `chat_session_analytics` route handler passes the following keys to `templates/chat_session/analytics.html`:

| Key | Type | Description |
|---|---|---|
| `session` | `ChatSession` | ORM object with session metadata |
| `analytics` | `RunAnalytics \| None` | `None` when 5K guard or no turns |
| `analytics_skipped` | `bool` | `True` when `total_turn_count > 5000` |
| `analytics_empty` | `bool` | `True` when `evaluated_count == 0` and not skipped |
| `turn_rows` | `list[dict]` | Turn Explorer rows from `turn_explorer_view()` |
| `declared_dims` | `list[str]` | Declared parameter names from session evaluator snapshot |
| `total_turns` | `int` | Total turn count (completed + failed + in-progress) |
| `completed_turns` | `int` | Completed (non-error) turn count |
| `failed_turns` | `int` | Failed turn count |
| `tooltip_copy` | `dict[str, str]` | Canonical metric explanation strings keyed by label |

### tooltip_copy dict

```python
TOOLTIP_COPY = {
    "Mean": "The average score for this parameter across all turns. Your baseline answer to \"how well did the chatbot perform on this dimension?\"",
    "Median": "The middle score when all turns are ranked from lowest to highest. If the median is noticeably lower than the mean, a small number of high-scoring turns are inflating the average...",
    "Min": "The lowest score any single turn received on this parameter. Represents the worst-case performance observed in this session.",
    "Max": "The highest score any single turn received on this parameter. Represents the best-case performance observed in this session.",
    "Range": "The gap between the best and worst scores (Max minus Min). A large range means performance was inconsistent...",
    "σ": "Measures how spread out the scores are around the average. A low σ means most turns scored close to the mean — predictable, consistent behaviour...",
    "Overall Mean Score": "The average quality score across every turn and every evaluation parameter in this session...",
    "Overall Verdict Distribution": "How the evaluator classified each turn overall...",
}
```

Full canonical text from spec section "Metric Explanations — Canonical Copy."
