# Feature Specification: Live Chat Session Analytics (Module 19)

**Feature Branch**: `019-live-chat-analytics`

**Created**: 2026-07-08

**Status**: Draft

**Depends On**: 017 (Live Chat & Real-Time Evaluation), 018 (Job Run Analytics Dashboard)

**Input**: Design decisions locked in session 2026-07-08. The live chat analytics page surfaces the same analytical report defined in 018 for a `ChatSession` rather than a batch `Job`. It consumes the shared `RunAnalytics` engine introduced in 018 by mapping `ChatSession → ChatTurn → ChatTurnResult` to the engine's `ScoreEntry` input shape.

> **Parent context**: This module extends `specs/017-live-chat-evaluation` and reuses the `RunAnalytics` engine defined in `specs/018-job-run-analytics-dashboard`. All 017 FR-LC- requirements remain in force. All analytics computation rules (FR-010 through FR-014, FR-028 through FR-031 in 018) apply unchanged — this spec covers only the surface differences introduced by the live chat data model and page context.

---

## Clarifications

### Session 2026-07-08 — Design decisions locked

**Page placement:**
- Q: Where does the live chat analytics page sit relative to the session view? → A: Option A — a separate analytics page at `/chat/{session_id}/analytics`, linked from the session view. It is not embedded in the chat interface and does not replace any part of the session view.

**Shared engine:**
- Q: Is the analytics computation shared with the batch job dashboard? → A: Yes. The `RunAnalytics` engine defined in 018 is called directly. The live chat route handler maps the `ChatSession` data model to the engine's `ScoreEntry` input shape. No new computation logic is introduced in this module.

**Download availability:**
- Q: Are CSV and JSON downloads restricted to terminal sessions only (as in 018)? → A: No. Live chat sessions have no terminal state — they are `active` from creation until deletion (per 017 FR-LC-005). Downloads follow the same rule as the existing export (017 FR-LC-041): always available from any active session.

**In-progress turns and downloads:**
- Q: How are in-progress turns handled in downloads? → A: Consistent with 017 FR-LC-041 — in-progress turns are excluded from downloads. Only completed and failed turns are included.

**5,000 threshold:**
- Q: Does the 5,000-unit hard limit from 018 FR-031 apply to chat sessions? → A: Yes, applied to `total_turn_count`. Sessions are unlikely to exceed this threshold in practice (sessions are described as accumulating 100+ turns across months of use) but the guard is included for consistency.

**Filename convention:**
- Q: What filename pattern for CSV and JSON downloads? → A: `{sanitised_session_name}-results.csv` / `{sanitised_session_name}-results.json`, where sanitised means: lowercase, spaces replaced with hyphens, non-alphanumeric characters stripped. Fallback: `session-{session_id[:8]}-results.csv` when the session name is empty or produces an empty sanitised string.

---

## Route

`GET /chat/{session_id}/analytics`

- Accessible to the session owner only. Enforces the same owner-only access rule as the session chat interface (017 FR-LC-008). Admins cannot access another user's analytics page.
- Computes `RunAnalytics` server-side at page load.
- Renders the analytics template with `RunAnalytics` output plus session metadata.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Navigate to the analytics page from a session (Priority: P1)

A tester has completed several turns in a live chat session and wants to see an analytical summary across all their conversations. They click an "Analytics" link on the session view, which opens the session analytics page. The page shows a Session Overview with aggregate stats, a Parameter Breakdown with per-parameter distributions, and a Turn Explorer table listing all evaluated turns.

**Why this priority**: The analytics page has no entry point without the session-view link. Both the link and the page are required together.

**Independent Test**: With a session of at least 10 completed turns, click the Analytics link from the session view, verify the page loads with correct session metadata and that the turn count matches the number of completed turns.

**Acceptance Scenarios**:

1. **Given** a tester is on their session's chat interface, **When** they click the Analytics link, **Then** they are taken to `/chat/{session_id}/analytics` without leaving or disrupting the session state.
2. **Given** a tester navigates directly to `/chat/{session_id}/analytics` for a session they do not own, **Then** the system rejects the request (403 or redirect), consistent with 017 FR-LC-008.
3. **Given** a tester is on the analytics page, **When** they click "Back to Session", **Then** they are returned to the session chat interface.

---

### User Story 2 — Review per-parameter quality statistics across all session turns (Priority: P1)

A tester who has explored a chatbot across 30 turns wants to know how consistently the evaluator has scored each parameter. The Parameter Breakdown section shows one block per declared parameter — Mean, Median, Min, Max, Range, σ as stat tiles, a histogram with ±1σ bands, and (for upgraded evaluators) a verdict distribution tile. They spot that "Accuracy" has a high standard deviation and a bimodal histogram — a signal that the chatbot performs inconsistently on this dimension.

**Why this priority**: The parameter breakdown is the primary analytical value of the page.

**Independent Test**: With a session whose evaluator declares at least two parameters and whose turns produce varied scores, verify stat tile values match independent calculations against the raw turn data.

**Acceptance Scenarios**:

1. **Given** a session with completed evaluated turns, **When** the tester views the Parameter Breakdown, **Then** one block renders per declared parameter in declared-dimension order; each block shows Mean, Median, Min, Max, Range, and σ in raw values.
2. **Given** a session whose evaluator emits per-parameter `verdict` (v2 contract), **When** the tester views a parameter block, **Then** a verdict distribution tile shows count and percentage per distinct verdict value for that parameter.
3. **Given** a session whose evaluator does not emit per-parameter `verdict` (v1 contract), **When** the tester views a parameter block, **Then** the verdict distribution tile renders a visible "not available" placeholder.
4. **Given** all turns in a session errored before evaluation, **When** the tester views the Parameter Breakdown, **Then** it renders an informational placeholder; the sidebar anchor remains present but is visually muted.
5. **Given** a session with more than 5,000 turns, **When** the analytics page loads, **Then** the Parameter Breakdown section displays a clear message stating the analytics report is unavailable for sessions exceeding 5,000 turns and directs the tester to the CSV or JSON export.

---

### User Story 3 — Browse individual turns analytically (Priority: P2)

A tester wants to identify which specific turns produced poor scores on a parameter. In the Turn Explorer section, they filter by `fail` verdict, scan the visible rows, and expand a row to see the full assembled response and per-parameter scoring detail.

**Why this priority**: The Turn Explorer connects aggregate analytics back to individual evidence.

**Independent Test**: With a session containing turns of varied verdicts including at least one failed turn, apply the verdict filter and verify only matching turns appear; expand a row and verify the full artifacts are visible.

**Acceptance Scenarios**:

1. **Given** the tester views the Turn Explorer, **Then** one row per completed or failed turn is shown, ordered by turn index ascending.
2. **Given** the tester applies a verdict filter, **When** the filter is active, **Then** only turns matching the selected verdict values are shown and a "Visible: N of M" indicator reflects the active filter.
3. **Given** the tester expands a row, **Then** the full user message, assembled chatbot response, normalized contract, and evaluation result are visible in the expanded section.
4. **Given** a turn has `status = failed`, **When** it appears in the Turn Explorer, **Then** it shows the error stage and error details in place of evaluation scores.

---

### User Story 4 — Export session results for external analysis (Priority: P2)

A tester wants to load their session's evaluation results into Power BI. From the sidebar, they download the CSV (long format, one row per turn-parameter pair) and the JSON (nested by turn). Both are available immediately regardless of whether the session is still active.

**Why this priority**: Export portability is the same requirement as in 018 and is the mechanism for integrating live chat findings into broader quality reporting.

**Independent Test**: Download both formats from a session with at least five completed turns and two declared parameters. Verify CSV row count equals (completed-turn count × parameter count), verify JSON structure matches the locked schema, verify the filename follows the convention.

**Acceptance Scenarios**:

1. **Given** a tester clicks Download CSV, **Then** a `.csv` file is downloaded with one row per turn-parameter pair using the schema defined in FR-012; in-progress turns are excluded.
2. **Given** a tester clicks Download JSON, **Then** a `.json` file is downloaded as an array of turn objects using the schema defined in FR-013; in-progress turns are excluded.
3. **Given** the session name is "My Chatbot Test", **When** either file is downloaded, **Then** the filename is `my-chatbot-test-results.csv` / `my-chatbot-test-results.json`.
4. **Given** the session has no completed turns (e.g., all in-progress or all failed before evaluation), **When** the tester downloads CSV, **Then** a file is produced with only the header row; no error is raised.

---

## Functional Requirements

### Route & Access

**FR-001** The system MUST expose a `GET /chat/{session_id}/analytics` route that renders the session analytics page.

**FR-002** Access MUST be restricted to the session owner. A request from a non-owner (including admins) MUST be rejected with a 403 response or redirect. This is consistent with 017 FR-LC-008.

**FR-003** The analytics page MUST be linked from the session chat interface view via a clearly labelled "Analytics" affordance (link or button). Clicking it navigates to the analytics page without modifying session state.

**FR-004** The analytics page MUST include a "Back to Session" link that returns the user to the session chat interface (`/chat/{session_id}`).

---

### Page Layout

**FR-005** The analytics page MUST follow the same single-scrolling-view layout defined in 018 FR-001, with a sticky left-hand sidebar. No tab strip.

**FR-006** The sidebar MUST contain:
- Section anchor links: Session Overview, Parameter Breakdown, Turn Explorer
- Action buttons: Print, Download CSV, Download JSON
The sidebar implements scrollspy as defined in 018 FR-026. Download buttons are always active (no terminal-state restriction applies to live chat sessions).

---

### Session Overview Section

**FR-007** The Session Overview section MUST display session metadata: session name, connector name, evaluator name, session creation date, total turn count, and failed turn count.

**FR-008** The Session Overview section MUST display an overall verdict distribution tile. The tile shows, for each distinct `overallVerdict` value observed across the session's evaluated turns, a count and a percentage. Failed turns (where evaluation did not complete) do not contribute to this distribution.

**FR-009** The Session Overview section MUST display an overall mean score tile. The value is the arithmetic mean of all `score` values across all `evaluationResult.parameters` entries for all turns with valid evaluation results.

---

### RunAnalytics Engine — Data Mapping

**FR-010** The route handler MUST map `ChatSession → ChatTurn → ChatTurnResult` to the `ScoreEntry` input shape defined in 018 before calling the shared `RunAnalytics` engine. The mapping is:

| `ScoreEntry` field | Source |
|---|---|
| `parameter_name` | `ChatTurnResult.evaluationResult.parameters[n].parameter_name` |
| `score` | `ChatTurnResult.evaluationResult.parameters[n].score` |
| `reasoning` | `ChatTurnResult.evaluationResult.parameters[n].reasoning` |
| `verdict` | `ChatTurnResult.evaluationResult.parameters[n].verdict` (optional) |
| `overall_verdict` | `ChatTurnResult.evaluationResult.overallVerdict` |
| `error` | `ChatTurn.status == 'failed'` |

**FR-011** Parameter discovery follows the declared dimensions from the session's snapshotted evaluator configuration (equivalent to `evaluatorDeclaredScoringDimensions` in the batch model), in declared order. Parameters present in results but absent from the declared list are appended and flagged as unexpected.

---

### Parameter Breakdown Section

**FR-012** The Parameter Breakdown section MUST follow all rules defined in 018 FR-015 through FR-019 and FR-030 through FR-031, with "utterances" replaced by "turns" throughout:

- One block per discovered parameter in declared order.
- Each block: six stat tiles (Mean, Median, Min, Max, Range, σ in raw values), histogram (10 CSS/HTML buckets, min-max normalised, raw x-axis labels, ±1σ bands), verdict distribution tile or "not available" placeholder.
- Empty state (zero evaluated turns): informational placeholder replaces section body; sidebar anchor visually muted.
- Scale guard: when `total_turn_count > 5000`, analytics computation is skipped and a clear message replaces the section body directing the user to exports. Session Overview continues to render.

---

### Turn Explorer Section

**FR-013** The Turn Explorer section MUST display a table with one row per `ChatTurn` (both completed and failed turns), ordered by turn index ascending.

**FR-014** Each row MUST display the following columns:

| Column | Source | Notes |
|---|---|---|
| Turn # | `ChatTurn` sequence index | Sortable |
| User Message | `ChatTurn.user_message_text` | Truncated to 200 chars; full text in row expand |
| Assembled Response | `ChatTurnResult.assembled_chatbot_response` | Truncated to 200 chars; full text in row expand |
| Overall Verdict | `evaluationResult.overallVerdict` | Styled badge; sortable |
| Scores | `evaluationResult.parameters` | Per-parameter list; includes inline `verdict` when present (v2 contract) |
| Error | `ChatTurn.status` / `ChatTurnResult.error_stage` | Shown only when turn failed |

**FR-015** The Turn Explorer MUST support:
- Verdict filter: filter by one or more overall verdict values
- Error-only toggle: show only failed turns
- Free-text search: across user message and assembled response text
- Sort: by turn index or verdict (ascending/descending)
- "Visible: N of M" indicator when any filter or search is active

**FR-016** Each row MUST be expandable to reveal the full user message, assembled chatbot response, normalized Standard Evaluation Contract, and full evaluation result. The expand section renders large JSON artifacts in a readable form with a copy-to-clipboard affordance, consistent with 017 and 004 FR-008 trace expand behaviour.

**FR-017** In-progress turns (status `in_progress`) MUST NOT appear in the Turn Explorer table. Only completed and failed turns are shown.

---

### Exports

**FR-018** The Print action MUST call `window.print()`. A dedicated print stylesheet MUST hide the sidebar and page navigation chrome and insert page breaks before the Parameter Breakdown section and before the Turn Explorer section. Consistent with 018 FR-022.

**FR-019** The Download CSV action MUST produce a `.csv` file in long format. The filename is `{sanitised_session_name}-results.csv` where sanitised means: lowercase, spaces → hyphens, non-alphanumeric characters stripped. Fallback: `session-{session_id[:8]}-results.csv`. Schema:

| Column | Source |
|---|---|
| `turnIndex` | `ChatTurn` sequence index |
| `userMessage` | `ChatTurn.user_message_text` |
| `assembledResponse` | `ChatTurnResult.assembled_chatbot_response` |
| `overallVerdict` | `evaluationResult.overallVerdict` |
| `parameterName` | `evaluationResult.parameters[n].parameter_name` |
| `score` | `evaluationResult.parameters[n].score` |
| `verdict` | `evaluationResult.parameters[n].verdict` — empty string when absent |
| `reasoning` | `evaluationResult.parameters[n].reasoning` |

One row per turn-parameter pair. Failed turns are included with error details in `overallVerdict` and empty parameter columns. In-progress turns are excluded.

**FR-020** The Download JSON action MUST produce a `.json` file using the same filename base as FR-019 with `.json` extension. Schema:

```json
[
  {
    "turnIndex": number,
    "userMessage": "string",
    "assembledResponse": "string | null",
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
]
```

The `verdict` key inside each parameter object MUST be omitted (not null) when the stored entry does not contain it. The `parameters` array is empty for failed turns. In-progress turns are excluded.

**FR-021** Both CSV and JSON downloads MUST be available at any time regardless of session activity state. There is no terminal-state restriction. This follows 017 FR-LC-041.

---

### Metric Explanations

**FR-024** Each stat tile in a parameter block MUST display an info icon (ⓘ) adjacent to the metric label. On hover (desktop) or tap (touch), the icon MUST show a tooltip or popover containing the canonical explanation for that metric as defined in the Metric Explanations section below. Identical requirement to 018 FR-032.

**FR-025** The Parameter Breakdown section MUST include a collapsible "How to read this report" guide panel positioned before the first parameter block. The panel MUST:
- Be expanded by default on first page load.
- Collapse on user interaction and remain collapsed for the duration of the browser session (via `sessionStorage`).
- Contain an explanation of each metric using the canonical copy defined in the Metric Explanations section below, with "turns" substituted for "responses" throughout.

**FR-026** The Overall Mean Score tile and Overall Verdict Distribution tile in the Session Overview section MUST each display an info icon (ⓘ) adjacent to the tile label. On hover or tap, the icon MUST show a tooltip containing the canonical explanation defined in the Metric Explanations section below.

---

### Computation

**FR-022** All metric aggregations MUST be computed server-side at page load by the shared `RunAnalytics` engine defined in 018. No new computation logic is introduced in this module. No client-side aggregation. No separate analytics API endpoint.

**FR-023** Analytics computation MUST be scoped to turns with `status = completed` and a non-null `ChatTurnResult.evaluationResult`. Failed turns contribute to error count in Session Overview but not to any score or verdict metric.

---

## Differences from 018 (Batch Analytics)

This table documents every point where 019 behaviour diverges from 018 for implementers.

| Concern | 018 (Batch) | 019 (Live Chat) |
|---|---|---|
| Route | Detail page (replaces existing layout) | `/chat/{session_id}/analytics` (new page) |
| Context header section | Job Overview | Session Overview |
| Unit of analysis | Utterance | ChatTurn |
| Data source — scores | `EvaluationResult.evaluation_scores` | `ChatTurnResult.evaluationResult.parameters` |
| Data source — overall verdict | `EvaluationResult.evaluation_verdict` | `ChatTurnResult.evaluationResult.overallVerdict` |
| Declared dimensions source | `Job.evaluatorDeclaredScoringDimensions` | Session evaluator snapshot |
| Download availability | Terminal jobs only | Always available |
| In-progress exclusion | N/A (no in-progress utterances) | In-progress turns excluded from table and exports |
| 5K threshold unit | `total_utterance_count` | `total_turn_count` |
| CSV column `utteranceText` | ✓ | — |
| CSV column `testId` | ✓ | — |
| CSV column `chatbotResponse` | ✓ | — |
| CSV column `turnIndex` | — | ✓ |
| CSV column `userMessage` | — | ✓ |
| CSV column `assembledResponse` | — | ✓ |
| Explorer table | Utterance table (existing, preserved from 004) | Turn Explorer (new) |
| Explorer row expand | Raw chatbot response + normalized contract + evaluation result | User message + assembled response + normalized contract + evaluation result |
| Filename base | `{source_csv_name_without_ext}` | `{sanitised_session_name}` |

---

## Metric Explanations — Canonical Copy

The following copy is the canonical text for tooltips and the "How to read this report" guide panel for the live chat analytics page. The wording is identical to 018 with "responses" replaced by "turns" throughout. Implementers MUST use this exact wording.

### Session Overview Metrics

**Overall Mean Score**
The average quality score across every turn and every evaluation parameter in this session. Think of it as the overall grade for the chatbot — closer to the evaluator's maximum is better.

**Overall Verdict Distribution**
How the evaluator classified each turn overall — for example, how many Passed, how many triggered a Warning, how many Failed. A quick summary of the session's quality at a glance.

### Parameter Breakdown Metrics

**Mean**
The average score for this parameter across all turns. Your baseline answer to "how well did the chatbot perform on this dimension?"

**Median**
The middle score when all turns are ranked from lowest to highest. If the median is noticeably lower than the mean, a small number of high-scoring turns are inflating the average. If the median is higher than the mean, a few poor turns are dragging it down. Mean and median close together means the scores are consistently spread.

**Min**
The lowest score any single turn received on this parameter. Represents the worst-case performance observed in this session.

**Max**
The highest score any single turn received on this parameter. Represents the best-case performance observed in this session.

**Range**
The gap between the best and worst scores (Max minus Min). A large range means performance was inconsistent — some turns scored well, others did not. A small range means the chatbot performed at a similar level across all turns.

**σ (Standard Deviation)**
Measures how spread out the scores are around the average. A low σ means most turns scored close to the mean — predictable, consistent behaviour. A high σ means scores varied widely — some turns were much better or worse than average. When comparing two parameters with the same mean, the one with the lower σ is more reliable.

**Score Distribution**
Shows where scores clustered across the full range. Bars to the right mean most turns scored high; bars to the left mean most scored low. A single tall bar means highly consistent scores; bars spread across the chart mean high variability. The shaded band marks where the middle approximately 68% of scores fall (±1 standard deviation from the mean) — scores outside this band are outliers worth investigating.

**Verdict Distribution**
How the evaluator classified individual turns for this specific parameter — for example, how many were rated Pass, Warning, or Fail. Tells you whether quality issues on this parameter are isolated incidents or a systematic pattern. Shown only when the evaluator provides per-parameter verdicts; otherwise displayed as "not available."

---

## Non-Goals (MVP)

- Multi-evaluator support — inherited non-goal from 018.
- Server-side PDF generation — browser print only.
- Live refresh of analytics — computed once at page load.
- Cross-session comparison.
- Analytics for sessions the requesting user does not own.
- Turn range or date-range scoping on exports — all turns always included (consistent with 017 FR-LC-041).
- Replay of individual turns from within the analytics page — session replay is a 017 non-goal.
