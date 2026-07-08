# Research: Live Chat Session Analytics (019)

**Generated**: 2026-07-08 | **Plan**: [plan.md](plan.md)

All decisions below were resolved during Phase 0 research against the existing codebase and the 018 plan.

---

## Decision 1 — Route path convention

**Decision**: `GET /chat/sessions/{session_id}/analytics` with handler name `chat_session_analytics`.

**Rationale**: All existing chat session routes follow the `/chat/sessions/{session_id}` prefix pattern (e.g., `/chat/sessions/{session_id}/turns`, `/chat/sessions/{session_id}/export`). The spec document uses `/chat/{id}/analytics` as a shorthand, but the implemented path must match the codebase convention. The handler name follows the existing `chat_session_*` naming pattern in `routes.py`.

**Alternatives considered**:
- `/chat/{session_id}/analytics` — matches spec shorthand but deviates from the codebase `/chat/sessions/` prefix used by every other session route.
- `/chat/analytics/{session_id}` — resource-last URL style; inconsistent with existing routes.

---

## Decision 2 — Shared engine import path

**Decision**: Import directly from `harness.ui.detail.analytics`:

```python
from harness.ui.detail.analytics import ScoreEntry, RunAnalytics, compute_analytics
```

**Rationale**: The `RunAnalytics` engine is defined in `harness.ui.detail.analytics` (feature 018). Importing from there avoids any duplication. The import works because both `harness.ui.detail` and `harness.ui.chat_session` are sub-packages of `harness.ui` — the import is within the same application. There is no circular import risk because `analytics.py` has no ORM or UI imports.

**Alternatives considered**:
- Move the engine to a shared `harness.analytics` package — premature; 018 placed it in `detail.analytics` by design as the canonical location; moving it would be a breaking refactor of 018.
- Duplicate the engine code in `chat_session/analytics.py` — explicitly rejected in the 019 spec (no duplication of computation logic).

---

## Decision 3 — ORM data access for all turns (no 50-turn limit)

**Decision**: Load all turns for the session (no limit), with `ChatTurnResult` and `ChatTurn.status` eager-loaded, in `created_at` ascending order. Use `selectinload` for `turn.result` to avoid N+1 queries.

**Rationale**: The chat interface loads only the 50 most recent turns (per 017 FR-LC-031). The analytics page must aggregate across all turns in the session regardless of count. The existing `chat_session_repository.get_session()` loads the session but not its turns eagerly. A new repository query or an inline SQLAlchemy query in the route handler is needed.

**Implementation**: Add a method `ChatSessionRepository.get_turns_with_results(session_id: str) -> list[ChatTurn]` that returns all non-in-progress turns ordered by `created_at ASC` with `result` selectin-loaded.

**Alternatives considered**:
- Reuse `interface.html`'s turn-load query — it has a `LIMIT 50`; that limit cannot be applied here.
- Load turns via `session.turns` relationship — the relationship is defined but not guaranteed to be eager-loaded at the session query point; explicit `selectinload` is safer.

---

## Decision 4 — final_evaluation_result field mapping

**Decision**: `ChatTurnResult.final_evaluation_result` is the full evaluator JSON contract. The `parameters` array is extracted as:

```python
result_json = turn.result.final_evaluation_result or {}
params = result_json.get("parameters", [])
overall_verdict = result_json.get("overallVerdict")
```

Each entry in `params` maps to a `ScoreEntry` with `parameter_name`, `score`, `reasoning`, and optional `verdict`.

**Rationale**: `final_evaluation_result` stores the complete evaluator contract including `overallVerdict` and `parameters`. This mirrors the batch system's `evaluation_scores` list, but wrapped in a top-level contract object. The mapping is documented in the 019 spec's data mapping table.

**Alternatives considered**:
- Extract from `EvaluationEvent` rows with `event_type == "final"` — redundant; `final_evaluation_result` is already extracted from the `final` event and persisted to the column at turn completion (017 FR-LC-037).

---

## Decision 5 — Download availability (no terminal gate)

**Decision**: Both CSV and JSON downloads are always available for any active session. The sidebar download buttons are never disabled. In-progress turns are excluded from downloads.

**Rationale**: Live chat sessions have no terminal state (017 FR-LC-005 — sessions are `active` from creation until deletion). The terminal-only gate from 018 is specific to batch jobs. The 019 spec explicitly overrides this: "Downloads are available at any time regardless of session activity state. There is no terminal-state restriction." Consistent with the existing export route (017 FR-LC-041 already exports at any time).

**Alternatives considered**:
- Apply terminal-only gate — rejected: sessions never reach a terminal state; this would make downloads permanently unavailable.

---

## Decision 6 — Filename sanitisation for session names

**Decision**:

```python
import re

def _sanitise_session_name(name: str) -> str:
    name = name.lower().strip()
    name = name.replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or None
```

Fallback when sanitised name is empty: `session-{session_id[:8]}`.

Filename pattern: `{sanitised_name}-results.csv` / `{sanitised_name}-results.json`.

**Rationale**: Session names are free-form user input (017 FR-LC-004 — no uniqueness constraint, no format constraint). They can contain spaces, punctuation, unicode. A simple sanitiser produces safe, readable filenames. The double-hyphen collapse prevents `--` artifacts from consecutive special chars.

**Alternatives considered**:
- Use `session_id[:8]` always (no sanitisation) — less human-readable; the session name is more useful for identifying the file.
- URL-encode the name — produces `%20` and `%2C` in filenames; less readable in file managers.

---

## Decision 7 — Turn Explorer: include failed turns, exclude in-progress

**Decision**: Turn Explorer shows completed and failed turns. In-progress turns are excluded. The filter is `ChatTurn.status in ("completed", "failed")`.

**Rationale**: Failed turns carry error stage and error details useful for diagnosis. The spec FR-017 explicitly states "in-progress turns MUST NOT appear." Completed and failed turns have stable persisted results and are safe to display.

**Alternatives considered**:
- Show only completed turns — loses visibility into failure patterns.
- Show all turns including in-progress — contradicts FR-017 and produces incomplete rows.

---

## Decision 8 — CSS reuse from 018

**Decision**: No new CSS classes are added to `harness.css` for feature 019. All CSS classes added by 018 (`.detail-layout`, `.detail-sidebar`, `.detail-main`, `.stat-tile-grid`, `.stat-tile`, `.histogram-wrap`, `.histogram-bar`, `.sigma-band`, `.histogram-xaxis`, `.info-icon`, `.analytics-guide`, `@media print`) are directly reused in the 019 template `analytics.html`.

**Rationale**: The analytics page layout is identical to the batch analytics layout in 018. Reusing CSS classes avoids duplication and ensures visual consistency. Both pages are part of the same application with a shared stylesheet.

**Alternatives considered**:
- Separate CSS prefix (e.g., `.chat-analytics-*`) — unnecessary duplication; the visual design is identical.

---

## Decision 9 — Access control: analytics page

**Decision**: Analytics page is restricted to the **session owner only**. Admins cannot access another user's analytics page. Reuse the existing `_require_session(repo, session_id, user)` helper from `routes.py`, which already enforces owner scope (raises 404 for non-owners; admin bypass is explicitly **not** applied for this route).

**Rationale**: The 019 spec FR-002 states "Access MUST be restricted to the session owner... A request from a non-owner (including admins) MUST be rejected." The existing `_require_session` helper accepts an `owner_scope` parameter. Passing `owner_oid=_owner_oid(user)` (not `None`) enforces owner-only access consistently with the session interface route.

**Alternatives considered**:
- Allow admins to view analytics — explicitly prohibited by the spec.

---

## Decision 10 — Repository method for analytics data access

**Decision**: Add a new method to `ChatSessionRepository`:

```python
def get_turns_with_results(self, session_id: str) -> list[ChatTurn]:
    """Return all non-in-progress turns for a session, ordered by created_at ASC,
    with result and evaluation_events selectin-loaded."""
```

This loads all completed and failed turns with their `ChatTurnResult` and is used exclusively by the analytics route. It does not have a `LIMIT` clause.

**Rationale**: No existing repository method provides this. The closest is the turn-load in `chat_interface` which has a `LIMIT 50` applied at query time. Adding a clean repository method keeps the route handler thin and makes the query independently testable.

**Alternatives considered**:
- Inline query in the route handler — acceptable but less testable; the repository pattern is established in the project.
- Load via `session.turns` relationship with Python-side filtering — relationship may trigger lazy loads; explicit `selectinload` with a targeted query is more predictable.
