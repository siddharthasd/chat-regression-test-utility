"""Job Execution Engine (Module 10) — the orchestrator.

Turns a queued Job into a persisted set of EvaluationResults by driving the
per-row connector→evaluator pipeline. Reuses 007/008 (dispatch + validation),
009 (persistence + lifecycle), and the in-memory password store (011 FR-015)::

    from harness.orchestrator import enqueue_job, run_job, reconcile_orphans
    reconcile_orphans()   # at startup (wired into bootstrap)
    enqueue_job(job_id)   # async start from the wizard
"""

from __future__ import annotations

from harness.orchestrator.engine import enqueue_job, reconcile_orphans, run_job
from harness.orchestrator.pipeline import process_row

__all__ = ["enqueue_job", "process_row", "reconcile_orphans", "run_job"]
