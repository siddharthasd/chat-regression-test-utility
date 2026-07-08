# Developer Quickstart: Live Chat Session Analytics (019)

**Generated**: 2026-07-08 | **Plan**: [plan.md](plan.md)

---

## Prerequisites

**Feature 018 must be implemented first.** This feature imports `ScoreEntry`, `RunAnalytics`, and `compute_analytics` from `harness.ui.detail.analytics`, which is created by 018. If 018 is not yet merged, implement 018 before starting 019.

No new Python dependencies are introduced. No Alembic migration is needed.

```powershell
# From repo root — standard setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

---

## Key Files to Know

| File | Role |
|---|---|
| `src/harness/ui/detail/analytics.py` | **FROM 018** — `ScoreEntry`, `RunAnalytics`, `compute_analytics`. Do not modify. |
| `src/harness/ui/chat_session/routes.py` | **EXTEND** — Add `chat_session_analytics`, `download_session_results_csv`, `download_session_results_json` route handlers. |
| `src/harness/ui/chat_session/view.py` | **EXTEND** — Add `score_entries_from_turns()`, `turn_explorer_view()`, `results_csv_builder()`, `results_json_builder()`, `_sanitise_session_name()`. |
| `src/harness/persistence/repositories/chat_session_repository.py` | **EXTEND** — Add `get_turns_with_results(session_id)` method. |
| `src/harness/ui/chat_session/templates/chat_session/analytics.html` | **NEW** — Full analytics page template. |
| `src/harness/ui/chat_session/templates/chat_session/interface.html` | **EXTEND** — Add "Analytics" link to session header. |
| `src/harness/ui/static/harness.css` | **NO CHANGE** — All CSS from 018 is reused. |
| `tests/integration/test_chat_session_analytics.py` | **NEW** — Integration tests. |

---

## Implementation Order

Build in this order to keep tests green at each step.

### Step 1 — Repository method

Add `get_turns_with_results()` to `ChatSessionRepository`. This is the only new DB query introduced by 019.

```python
from sqlalchemy.orm import selectinload

def get_turns_with_results(self, session_id: str) -> list[ChatTurn]:
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

Write a unit test for this method using an in-memory SQLite fixture. Verify:
- In-progress turns are excluded.
- Results ordered by `created_at`.
- `turn.result` is accessible without additional queries.

### Step 2 — View functions

Add to `src/harness/ui/chat_session/view.py`:

```python
import re
import csv
import json
import io

from harness.ui.detail.analytics import ScoreEntry, compute_analytics

def _sanitise_session_name(name: str) -> str | None:
    name = name.lower().strip()
    name = name.replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or None


def score_entries_from_turns(turns: list) -> list[ScoreEntry]:
    entries = []
    for turn in turns:
        if turn.status == "in_progress":
            continue
        is_error = turn.status == "failed"
        result = turn.result
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
                verdict=p.get("verdict"),
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


def turn_explorer_view(turns: list) -> list[dict]:
    rows = []
    for i, turn in enumerate(turns, start=1):
        if turn.status == "in_progress":
            continue
        result = turn.result
        result_json = (result.final_evaluation_result or {}) if result else {}
        params = result_json.get("parameters", [])
        scores = [
            {
                "name": p.get("parameter_name", ""),
                "score": p.get("score"),
                "reasoning": p.get("reasoning") or "",
                "verdict": p.get("verdict"),
            }
            for p in params if isinstance(p, dict)
        ]
        rows.append({
            "turn_index": i,
            "status": turn.status,
            "user_message": turn.user_message or "",
            "assembled_response": (result.assembled_response if result else None) or "",
            "overall_verdict": result_json.get("overallVerdict"),
            "scores": scores,
            "error_stage": (result.error_stage if result else None),
            "error_details": (result.error_details if result else None),
            "result_json_str": json.dumps(result_json, indent=2) if result_json else "{}",
        })
    return rows


def results_csv_builder(session, turns: list) -> tuple[str, str]:
    sanitised = _sanitise_session_name(session.session_name or "")
    if not sanitised:
        sanitised = f"session-{session.chat_session_id[:8]}"
    filename = f"{sanitised}-results.csv"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "turnIndex", "userMessage", "assembledResponse",
        "overallVerdict", "parameterName", "score", "verdict", "reasoning",
    ])

    for i, turn in enumerate(turns, start=1):
        if turn.status == "in_progress":
            continue
        result = turn.result
        result_json = (result.final_evaluation_result or {}) if result else {}
        params = result_json.get("parameters", [])
        overall_verdict = result_json.get("overallVerdict")
        assembled = (result.assembled_response if result else None) or ""

        if not params:
            writer.writerow([
                i,
                turn.user_message or "",
                assembled,
                overall_verdict or "",
                "", "", "", "",
            ])
        else:
            for p in params:
                if not isinstance(p, dict):
                    continue
                writer.writerow([
                    i,
                    turn.user_message or "",
                    assembled,
                    overall_verdict or "",
                    p.get("parameter_name", ""),
                    p.get("score", ""),
                    p.get("verdict", ""),
                    p.get("reasoning", ""),
                ])

    return filename, output.getvalue()


def results_json_builder(session, turns: list) -> tuple[str, str]:
    sanitised = _sanitise_session_name(session.session_name or "")
    if not sanitised:
        sanitised = f"session-{session.chat_session_id[:8]}"
    filename = f"{sanitised}-results.json"

    result_array = []
    for i, turn in enumerate(turns, start=1):
        if turn.status == "in_progress":
            continue
        result = turn.result
        result_json = (result.final_evaluation_result or {}) if result else {}
        params = result_json.get("parameters", [])
        parameters = []
        for p in params:
            if not isinstance(p, dict):
                continue
            entry = {
                "parameter_name": p.get("parameter_name", ""),
                "score": p.get("score"),
                "reasoning": p.get("reasoning") or "",
            }
            if "verdict" in p:
                entry["verdict"] = p["verdict"]
            parameters.append(entry)

        obj = {
            "turnIndex": i,
            "userMessage": turn.user_message or "",
            "assembledResponse": (result.assembled_response if result else None),
            "overallVerdict": result_json.get("overallVerdict"),
            "errorStatus": turn.status if turn.status == "failed" else None,
            "errorStage": (result.error_stage if result else None),
            "parameters": parameters,
        }
        result_array.append(obj)

    return filename, json.dumps(result_array, indent=2, ensure_ascii=False)
```

### Step 3 — Route handlers

Add to `src/harness/ui/chat_session/routes.py`:

```python
from harness.ui.detail.analytics import compute_analytics
from harness.ui.chat_session.view import (
    score_entries_from_turns,
    turn_explorer_view,
    results_csv_builder,
    results_json_builder,
)
from fastapi.responses import Response

TOOLTIP_COPY = {
    "Mean": "The average score for this parameter across all turns. Your baseline answer to \"how well did the chatbot perform on this dimension?\"",
    "Median": "The middle score when all turns are ranked from lowest to highest...",
    "Min": "The lowest score any single turn received on this parameter.",
    "Max": "The highest score any single turn received on this parameter.",
    "Range": "The gap between the best and worst scores (Max minus Min)...",
    "σ": "Measures how spread out the scores are around the average...",
    "Overall Mean Score": "The average quality score across every turn and every evaluation parameter in this session...",
    "Overall Verdict Distribution": "How the evaluator classified each turn overall...",
}

@router.get("/chat/sessions/{session_id}/analytics")
async def chat_session_analytics(
    request: Request,
    session_id: str,
    user=Depends(_require_auth),
):
    session = _require_session(repo, session_id, user)
    turns = repo.get_turns_with_results(session_id)

    total_turns = session.total_turn_count or 0
    completed_turns = sum(1 for t in turns if t.status == "completed")
    failed_turns = sum(1 for t in turns if t.status == "failed")
    declared_dims = session.evaluator_declared_scoring_dimensions or []

    if total_turns > 5000:
        analytics, analytics_skipped, analytics_empty = None, True, False
    else:
        entries = score_entries_from_turns(turns)
        evaluated = [e for e in entries if not e.error]
        if not evaluated:
            analytics, analytics_skipped, analytics_empty = None, False, True
        else:
            analytics = compute_analytics(entries, declared_dims)
            analytics_skipped = analytics_empty = False

    return templates.TemplateResponse("chat_session/analytics.html", {
        "request": request,
        "session": session,
        "analytics": analytics,
        "analytics_skipped": analytics_skipped,
        "analytics_empty": analytics_empty,
        "turn_rows": turn_explorer_view(turns),
        "declared_dims": declared_dims,
        "total_turns": total_turns,
        "completed_turns": completed_turns,
        "failed_turns": failed_turns,
        "tooltip_copy": TOOLTIP_COPY,
    })


@router.get("/chat/sessions/{session_id}/download-results.csv")
async def download_session_results_csv(
    request: Request,
    session_id: str,
    user=Depends(_require_auth),
):
    session = _require_session(repo, session_id, user)
    turns = repo.get_turns_with_results(session_id)
    filename, body = results_csv_builder(session, turns)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/chat/sessions/{session_id}/download-results.json")
async def download_session_results_json(
    request: Request,
    session_id: str,
    user=Depends(_require_auth),
):
    session = _require_session(repo, session_id, user)
    turns = repo.get_turns_with_results(session_id)
    filename, body = results_json_builder(session, turns)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

### Step 4 — interface.html link

Add an "Analytics" link to the session header in `interface.html`. Place it adjacent to other session action buttons (rename, export, delete):

```html
<a href="/chat/sessions/{{ session.chat_session_id }}/analytics"
   class="btn btn-sm btn-outline-secondary">
  Analytics
</a>
```

### Step 5 — Template (analytics.html)

Create `src/harness/ui/chat_session/templates/chat_session/analytics.html`. The template structure follows `detail/index.html` (018) with these substitutions:

| 018 (batch) | 019 (live chat) |
|---|---|
| `{% extends "base.html" %}` | same |
| Section heading: "Job Overview" | "Session Overview" |
| `meta.job_id`, `meta.status`, etc. | `session.chat_session_id`, `session.session_name`, etc. |
| Section heading: "Result Explorer" | "Turn Explorer" |
| Download `href`: `/jobs/{id}/download-results.csv` | `/chat/sessions/{id}/download-results.csv` |
| Download guard: `if meta.terminal` | No guard — always show active buttons |
| Back link: `href="/jobs"` | `href="/chat/sessions/{{ session.chat_session_id }}"` → "Back to Session" |
| `turn_rows` not present | `turn_rows` from `turn_explorer_view()` |

All CSS classes (`.detail-layout`, `.detail-sidebar`, `.detail-main`, `.stat-tile-grid`, `.stat-tile`, `.histogram-wrap`, `.histogram-bar`, `.sigma-band`, `.analytics-guide`, etc.) are reused unchanged.

Key template sections:

```html
{% extends "base.html" %}
{% block content %}
<div class="detail-layout">

  {# Sidebar #}
  <aside class="detail-sidebar">
    <nav class="sidebar-nav" id="sidebar-nav">
      <a href="#section-session-overview">Session Overview</a>
      <a href="#section-parameter-breakdown"
         {% if analytics_empty %}class="text-muted"{% endif %}>
        Parameter Breakdown
      </a>
      <a href="#section-turn-explorer">Turn Explorer</a>
    </nav>
    <div class="sidebar-actions mt-3">
      <button onclick="window.print()" class="btn btn-sm btn-outline-secondary">Print</button>
      <a href="/chat/sessions/{{ session.chat_session_id }}/download-results.csv"
         class="btn btn-sm btn-outline-primary">Download CSV</a>
      <a href="/chat/sessions/{{ session.chat_session_id }}/download-results.json"
         class="btn btn-sm btn-outline-primary">Download JSON</a>
    </div>
    <div class="mt-3">
      <a href="/chat/sessions/{{ session.chat_session_id }}"
         class="btn btn-sm btn-outline-secondary w-100">← Back to Session</a>
    </div>
  </aside>

  <main class="detail-main">

    {# Section 1: Session Overview #}
    <section id="section-session-overview">
      <h2>Session Overview</h2>
      {# session name, connector, evaluator, created_at, total_turns, failed_turns #}
      {# overall verdict distribution tile + overall mean score tile from analytics #}
    </section>

    {# Section 2: Parameter Breakdown — identical pattern to 018 #}
    <section id="section-parameter-breakdown">
      <h2>Parameter Breakdown</h2>
      {% if analytics_skipped %}
        <div class="alert alert-warning">
          Analytics are not available for sessions with more than 5,000 turns.
          Use Download CSV or Download JSON to analyse results externally.
        </div>
      {% elif analytics_empty %}
        <div class="alert alert-secondary">
          No evaluated results — all turns resulted in errors or are still in progress.
        </div>
      {% else %}
        {# Collapsible guide, stat tiles, histogram, verdict distribution — same as 018 #}
      {% endif %}
    </section>

    {# Section 3: Turn Explorer #}
    <section id="section-turn-explorer">
      <h2>Turn Explorer</h2>
      {# Filter bar: verdict filter, error-only toggle, free-text search, sort #}
      {# Table: turn_index, user_message (truncated), assembled_response (truncated),
                overall_verdict badge, scores list, error info #}
      {# Row expand: full user message, full assembled response,
                     normalized contract, evaluation result JSON + copy button #}
    </section>

  </main>
</div>

<script>
// Scrollspy — identical to 018
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

// Guide collapse — identical to 018 (sessionStorage key reused)
function toggleGuide() {
  const body = document.getElementById('analytics-guide-body');
  const collapsed = body.style.display === 'none';
  body.style.display = collapsed ? '' : 'none';
  sessionStorage.setItem('analytics-guide-collapsed', collapsed ? '0' : '1');
}
if (sessionStorage.getItem('analytics-guide-collapsed') === '1') {
  const b = document.getElementById('analytics-guide-body');
  if (b) b.style.display = 'none';
}

// Bootstrap tooltips
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-bs-toggle="tooltip"]')
    .forEach(el => bootstrap.Tooltip.getOrCreateInstance(el));
});

// Turn Explorer filters (client-side)
// Implement verdict filter, error-only toggle, free-text search as inline JS
// operating on the static turn_rows data rendered into the page.
</script>
{% endblock %}
```

---

## Running Tests

```powershell
# Integration tests for live chat analytics
pytest tests/integration/test_chat_session_analytics.py -v

# Full test suite
pytest
```

---

## Verifying the Feature Manually

1. Start the dev server: `uvicorn harness.ui:create_app --factory --reload`
2. Create a live chat session via the wizard and run at least 5 turns until they complete evaluation.
3. From the session interface, click the "Analytics" link — verify navigation to `/chat/sessions/{id}/analytics`.
4. Verify: Session Overview shows session name, turn counts, overall mean, and verdict distribution.
5. Verify: Parameter Breakdown shows one block per declared dimension with stat tiles, histogram, and ±1σ band.
6. Verify: guide panel is expanded on first visit; collapsing it persists within the tab session.
7. Verify: hovering ⓘ on a stat tile shows the canonical tooltip copy.
8. Verify: Turn Explorer shows all completed and failed turns ordered by index; no in-progress turns appear.
9. Verify: clicking Download CSV produces `{sanitised-name}-results.csv` with one row per turn-parameter pair.
10. Verify: clicking Download JSON produces the nested array format.
11. Verify: Print hides sidebar and inserts page breaks.
12. Verify: non-owner access rejected — log in as a different user, navigate directly to the URL, confirm 404 or redirect.
13. Verify 5K guard: update `total_turn_count` directly in the DB to 5001; reload analytics page and confirm the unavailability message.
14. Verify empty state: create a session where all turns fail before evaluation; confirm placeholder renders.
15. Verify "Back to Session" returns to `/chat/sessions/{id}` without disrupting session state.
