"""Dashboard projections + filter/sort/search helpers (002). Pure functions over Job rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from harness.persistence.enums import TERMINAL_STATUSES, JobStatus
from harness.persistence.models.chat_session import ChatSession

if TYPE_CHECKING:
    from harness.persistence.models import Job

#: Canonical status order for the filter UI + badge legend (FR-004).
STATUS_ORDER: tuple[str, ...] = tuple(s.value for s in JobStatus)

_DELETABLE = {JobStatus.FAILED.value, JobStatus.CANCELLED.value}


def _aware(dt: datetime) -> datetime:
    """Treat naive DB datetimes as UTC (SQLite stores naive)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def format_timestamp(dt: datetime | None, now: datetime) -> tuple[str, str]:
    """Hybrid timestamp (FR-003a): relative < 24h, absolute otherwise.

    Returns ``(display, title)`` where ``title`` is the alternate representation
    (shown on hover). ``("—", "")`` for a missing timestamp.
    """
    if dt is None:
        return "—", ""
    dt = _aware(dt)
    absolute = dt.strftime("%Y-%m-%d %H:%M")
    delta = now - dt
    seconds = delta.total_seconds()
    if 0 <= seconds < 86400:
        if seconds < 60:
            rel = "just now"
        elif seconds < 3600:
            n = int(seconds // 60)
            rel = f"{n} minute{'s' if n != 1 else ''} ago"
        else:
            n = int(seconds // 3600)
            rel = f"{n} hour{'s' if n != 1 else ''} ago"
        return rel, absolute
    return absolute, absolute


def _badge_class(status: str, failed: int) -> str:
    if status == JobStatus.COMPLETED.value and failed > 0:
        return "badge-completed-errors"
    return f"badge-{status}"


def _status_label(status: str, failed: int) -> str:
    if status == JobStatus.COMPLETED.value and failed > 0:
        return "Completed with errors"
    return status.replace("_", " ").capitalize()


def row_view(job: Job, now: datetime | None = None) -> dict:
    """Project a Job into the dashboard row dict (FR-003)."""
    now = now or datetime.now(UTC)
    failed = job.failed_count or 0
    created = format_timestamp(job.created_at, now)
    started = format_timestamp(job.started_at, now)
    completed = format_timestamp(job.completed_at, now)
    return {
        "job_id": job.job_id,
        "job_name": job.job_name,
        "status": job.status,
        "status_label": _status_label(job.status, failed),
        "badge_class": _badge_class(job.status, failed),
        "created_by": job.created_by,
        "created_at": created,
        "started_at": started,
        "completed_at": completed,
        "created_at_value": _aware(job.created_at),
        "started_at_value": _aware(job.started_at) if job.started_at else None,
        "completed_at_value": _aware(job.completed_at) if job.completed_at else None,
        "connector_name": job.connector_name,
        "processed": job.processed_count or 0,
        "total": job.total_utterance_count,
        "failed_count": failed,
        "harness_version": job.harness_version,
        "deletable": job.status in _DELETABLE or (
            job.status == JobStatus.COMPLETED.value and failed > 0
        ),
        "terminal": job.status in {s.value for s in TERMINAL_STATUSES},
    }


def apply_filters(
    rows: list[dict],
    *,
    statuses: list[str] | None = None,
    connectors: list[str] | None = None,
    created_bys: list[str] | None = None,
    q: str | None = None,
) -> list[dict]:
    """AND-combine the multi-select filters + case-insensitive name search (FR-006/007/008)."""
    needle = (q or "").strip().lower()
    out = []
    for r in rows:
        if statuses and r["status"] not in statuses:
            continue
        if connectors and r["connector_name"] not in connectors:
            continue
        if created_bys and r["created_by"] not in created_bys:
            continue
        if needle and needle not in (r["job_name"] or "").lower():
            continue
        out.append(r)
    return out


_SORT_KEYS = {
    "job_name": lambda r: (r["job_name"] or "").lower(),
    "status": lambda r: r["status"],
    "created_by": lambda r: (r["created_by"] or "").lower(),
    "created_at": lambda r: r["created_at_value"],
    "started_at": lambda r: r["started_at_value"] or datetime.min.replace(tzinfo=UTC),
    "completed_at": lambda r: r["completed_at_value"] or datetime.min.replace(tzinfo=UTC),
    "connector": lambda r: (r["connector_name"] or "").lower(),
    "failed_count": lambda r: r["failed_count"],
    "harness_version": lambda r: r["harness_version"] or "",
}


def sort_rows(rows: list[dict], sort: str | None, direction: str | None) -> list[dict]:
    """Sort by an underlying value (FR-009); default created_at desc (FR-009a)."""
    key = _SORT_KEYS.get(sort or "created_at", _SORT_KEYS["created_at"])
    reverse = (direction or "desc").lower() != "asc"
    return sorted(rows, key=key, reverse=reverse)


def distinct_facets(rows: list[dict]) -> dict:
    """Filter option sets from the persisted data (FR-006) — no registry consulted."""
    return {
        "statuses": [s for s in STATUS_ORDER if any(r["status"] == s for r in rows)],
        "connectors": sorted({r["connector_name"] for r in rows if r["connector_name"]}),
        "created_bys": sorted({r["created_by"] for r in rows if r["created_by"]}),
    }


def job_activity_view(job: "Job", now: datetime | None = None) -> dict:
    """Project a Job into the unified dashboard activity row."""
    now = now or datetime.now(UTC)
    failed = job.failed_count or 0
    raw_activity = job.completed_at or job.started_at or job.created_at
    activity_at = _aware(raw_activity) if raw_activity else datetime.min.replace(tzinfo=UTC)
    activity_display, activity_title = format_timestamp(raw_activity, now)
    processed = job.processed_count or 0
    total = job.total_utterance_count
    count_label = f"{processed}/{total if total is not None else '?'} utterances"
    terminal = job.status in {s.value for s in TERMINAL_STATUSES}
    can_download = terminal and processed > 0
    return {
        "type": "job",
        "id": job.job_id,
        "job_id": job.job_id,
        "name": job.job_name,
        "status": job.status,
        "status_label": _status_label(job.status, failed),
        "badge_class": _badge_class(job.status, failed),
        "connector_name": job.connector_name,
        "activity_at": activity_at,
        "activity_display": activity_display,
        "activity_title": activity_title,
        "count_label": count_label,
        "detail_url": f"/jobs/{job.job_id}/detail",
        "chat_url": None,
        "download_url": f"/jobs/{job.job_id}/download-results.csv",
        "can_download": can_download,
        "terminal": terminal,
        "deletable": job.status in _DELETABLE or (
            job.status == JobStatus.COMPLETED.value and failed > 0
        ),
    }


def session_activity_view(session: ChatSession, turn_count: int = 0, now: datetime | None = None) -> dict:
    """Project a ChatSession into the unified dashboard activity row."""
    now = now or datetime.now(UTC)
    activity_at = _aware(session.created_at)
    activity_display, activity_title = format_timestamp(session.created_at, now)
    count_label = f"{turn_count} turn{'s' if turn_count != 1 else ''}"
    sid = session.chat_session_id
    return {
        "type": "chat",
        "id": sid,
        "job_id": None,
        "name": session.session_name,
        "status": "active" if turn_count > 0 else "new",
        "status_label": "Active" if turn_count > 0 else "New",
        "badge_class": "badge-running" if turn_count > 0 else "badge-draft",
        "connector_name": session.connector_name or None,
        "activity_at": activity_at,
        "activity_display": activity_display,
        "activity_title": activity_title,
        "count_label": count_label,
        "detail_url": f"/chat/sessions/{sid}/analytics",
        "chat_url": f"/chat/sessions/{sid}",
        "download_url": f"/chat/sessions/{sid}/download-results.csv",
        "can_download": turn_count > 0,
        "terminal": True,
        "deletable": False,
    }
