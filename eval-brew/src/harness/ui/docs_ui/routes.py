"""Documentation viewer routes — readable by all roles."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from harness.ui._context import ctx
from harness.ui._templates import templates

router = APIRouter()

_DOCS_DIR = Path(__file__).parents[4] / "docs"

_GUIDES: dict[str, tuple[str, str]] = {
    "about": ("about.md", "About the Harness"),
    "csv-upload": ("csv-upload-guide.md", "CSV Upload Guide"),
    "connector-developer-guide": ("connector-developer-guide.md", "Connector Developer Guide"),
    "evaluator-developer-guide": ("evaluator-developer-guide.md", "Evaluator Developer Guide"),
    "solution-architecture": ("solution-architecture.md", "Solution Architecture"),
}

_RELEASES = [
    {
        "version": "3.2",
        "title": "Headless API & Security Hardening",
        "date": "17 July 2026",
        "badge_style": "background:#460073",
        "summary": "Programmatic job execution via a REST API for CI/CD integration, a self-contained Accenture design system with no external CDN dependency, and critical SSO identity and browser compatibility fixes.",
        "sections": [
            {
                "title": "New Features",
                "bullets": [
                    "Headless Execution API — Bearer JWT-authenticated REST endpoints to create jobs, poll status, and retrieve results programmatically without the UI. Enables CI/CD pipelines and automated regression runs.",
                    "POST /api/v1/jobs — create a job from a JSON payload with utterances, connector, and evaluator; returns a job ID.",
                    "GET /api/v1/jobs/{job_id}/status — poll job status and progress (queued, running, completed, failed).",
                    "GET /api/v1/jobs/{job_id}/results — retrieve full scored results as JSON once the job completes; includes a results_url linking to the analytics dashboard.",
                    "HARNESS_PUBLIC_URL environment variable — sets the base URL used in results_url for absolute links from external callers.",
                ],
            },
            {
                "title": "UI & Design System",
                "bullets": [
                    "Accenture Design System — self-contained CSS replacing Bootstrap CDN; zero external dependencies. Full Accenture purple spectrum, black navbar, neutral surface background, and Bootstrap-compatible utility class names so templates required no changes.",
                    "IE11 / Edge IE-compatibility mode fix — CSS literal-value fallbacks added to navbar and footer for environments where CSS custom properties are not supported; X-UA-Compatible meta tag added to force Edge out of IE rendering mode.",
                ],
            },
            {
                "title": "Security & Bug Fixes",
                "bullets": [
                    "SSO identity fix — wizard job creation and clone routes now record the authenticated user's Azure OID as the job owner instead of the container OS username. Jobs are now correctly scoped to the creating user on the dashboard.",
                    "RBAC enforcement confirmed — users whose enterprise ID is not in the user_registration table are redirected to /auth/unauthorised at login; every subsequent request re-validates OID against the RBAC table.",
                    "Headless API auth fix — corrected environment variable names and M2M audience resolution for Bearer JWT validation.",
                ],
            },
        ],
    },
    {
        "version": "3.1",
        "title": "Infrastructure & Dashboard",
        "date": "11 July 2026",
        "badge_style": "background:var(--color-primary)",
        "summary": "PostgreSQL support, structured startup observability, and a unified overview dashboard that brings job runs and chat sessions together on the landing page.",
        "sections": [
            {
                "title": "New Features",
                "bullets": [
                    "Unified overview dashboard — KPI tiles (Job Runs, Chat Sessions, Utterances, Turns) plus a combined Recent Activity feed across both job runs and chat sessions with one-click access to reports and downloads.",
                    "Filter pills on the activity feed (All / Jobs / Chat / Running / Failed) with client-side filtering — no page reload.",
                    "Quick-action buttons (+ New Job, + New Chat Session) always visible on the landing page.",
                    "Job Sessions list moved to /jobs; the root URL (/) is now the overview dashboard.",
                ],
            },
            {
                "title": "Infrastructure",
                "bullets": [
                    "PostgreSQL support alongside SQLite — switch databases by setting the DATABASE_URL environment variable.",
                    "Azure Container Apps deployment guide with PostgreSQL configuration.",
                    "Structured startup logging: backend type, migration revision, and orphan-turn recovery count emitted as structured JSON log lines on every startup.",
                    "PostgreSQL connection-pool safety hardening and test-isolation improvements.",
                ],
            },
        ],
    },
    {
        "version": "3.0",
        "title": "Analytics",
        "date": "9 July 2026",
        "badge_style": "background:#0057B8",
        "summary": "Deep analytics for both batch job runs and live chat sessions, plus a full Accenture brand alignment across the UI.",
        "sections": [
            {
                "title": "New Features",
                "bullets": [
                    "Job Run Analytics Dashboard — overall mean score, verdict distribution (pass/warn/fail), per-parameter stats (mean, median, min, max, stddev), histogram charts, and intent breakdown across up to 20 utterance intents.",
                    "Live Chat Analytics — session overview tiles, per-parameter score breakdowns with histograms, and a Turn Explorer table with per-turn filtering and score drill-in.",
                    "Analytics export: download evaluated results as CSV or JSON from both job and chat analytics pages.",
                    "utterance_intent field added to the evaluation contract, enabling intent-level breakdowns in analytics.",
                ],
            },
            {
                "title": "UI & Branding",
                "bullets": [
                    "Accenture brand alignment: Arial typeface, black navbar with purple accent, neutral surface background, and toned-down danger buttons.",
                    "Visual redesign: elevated white cards, purple primary brand colour, consistent badge and verdict colour system.",
                    "Evaluator developer guide corrected with accurate SSE protocol documentation.",
                ],
            },
        ],
    },
    {
        "version": "2.0",
        "title": "Live Chat Evaluation",
        "date": "2 July 2026",
        "badge_style": "background:#198754",
        "summary": "Real-time interactive chatbot evaluation — send messages, stream responses, and receive evaluation scores turn by turn without running a batch job.",
        "sections": [
            {
                "title": "New Features",
                "bullets": [
                    "Live Chat interface — multi-turn conversation with any registered connector, evaluated in real time via server-sent events (SSE).",
                    "Turn-by-turn evaluation: each response is scored by the evaluator immediately after streaming completes.",
                    "Dual view modes: User View (clean conversation) and Evaluator View (scores, reasoning, and evaluation trace visible inline).",
                    "Autoscroll and Turn N separator during live streaming for clear progress tracking.",
                    "5-step chat session wizard: name → connector → credentials → evaluator → review.",
                    "Chat Session list with sortable columns and per-session delete.",
                    "EvalBrew rebrand: new name, logo, and brand accent throughout the UI.",
                    "Documentation module: About EvalBrew, Solution Architecture, and developer guides accessible from the navbar.",
                ],
            },
        ],
    },
    {
        "version": "1.0-mvp",
        "title": "Foundation Release",
        "date": "21 June 2026",
        "badge_style": "background:#6c757d",
        "summary": "The initial production release — a complete batch regression testing harness for chatbot endpoints, from CSV upload through scored results export.",
        "sections": [
            {
                "title": "Core Testing",
                "bullets": [
                    "Batch job execution: upload a CSV of utterances, run them against a chatbot connector, evaluate each response, and download scored results.",
                    "Job creation wizard (5 steps): name → connector → CSV upload → evaluator → review.",
                    "Job execution engine with real-time progress tracking (utterance count, failed count) via live dashboard polling.",
                    "Job detail view with per-utterance traceability: request, response, evaluation contract, and per-parameter scores.",
                    "Results export in CSV, JSON, and ZIP formats.",
                    "Clone & Rerun: copy any completed or failed job with one click.",
                ],
            },
            {
                "title": "Connector & Evaluator Registry",
                "bullets": [
                    "Register, test, archive, and manage connector and evaluator endpoints.",
                    "OAuth2 client-credentials (M2M) auth mode for connectors and evaluators.",
                    "Test Connection button on registration forms with live response preview.",
                    "Standard Evaluation Contract: typed JSON schema shared between the engine and evaluators.",
                ],
            },
            {
                "title": "Platform",
                "bullets": [
                    "FastAPI + Jinja2 server-side-rendered UI with Bootstrap 5.",
                    "SQLite persistence with Alembic migrations.",
                    "Azure AD RBAC: admin and user roles with scoped job visibility.",
                    "Admin maintenance page: bulk-clear failed, cancelled, and completed jobs.",
                    "Tester identity stamped on every job for audit and filtering.",
                ],
            },
        ],
    },
]


@router.get("/docs/{guide}", name="docs_guide")
def docs_guide(request: Request, guide: str):
    entry = _GUIDES.get(guide)
    if entry is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    filename, title = entry
    try:
        content = (_DOCS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Guide file not found")
    return templates.TemplateResponse(
        request,
        "docs/guide.html",
        {"title": title, "markdown_content": content, **ctx(request)},
    )


@router.get("/release-notes", name="release_notes")
def release_notes(request: Request):
    return templates.TemplateResponse(
        request,
        "docs/release_notes.html",
        {"releases": _RELEASES, **ctx(request)},
    )
