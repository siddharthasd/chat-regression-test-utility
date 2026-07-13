"""Pydantic request/response schemas for the headless execution API (020)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ------------------------------------------------------------------ requests


class HeadlessTestCase(BaseModel):
    """One test case in a headless job submission."""

    model_config = ConfigDict(extra="allow")

    id: str
    input_message: str


class HeadlessJobSubmission(BaseModel):
    """POST /api/headless/jobs request body."""

    test_cases: list[HeadlessTestCase]
    connector_id: str
    evaluator_id: str
    source_system: str | None = None
    product_name: str | None = None
    feature_name: str | None = None


# ------------------------------------------------------------------ responses


class HeadlessJobSubmissionResponse(BaseModel):
    """Returned by POST /api/headless/jobs on success (201)."""

    job_id: str
    stream_url: str
    result_url: str


class FailedCase(BaseModel):
    """One entry in the top_failures list."""

    id: str
    input_message: str


class JobSummary(BaseModel):
    """Execution outcome summary — carried in terminal SSE events and result endpoint."""

    total: int
    passed: int
    failed: int
    top_failures: list[FailedCase]


class HeadlessJobResult(BaseModel):
    """Returned by GET /api/headless/jobs/{id}/result."""

    job_id: str
    status: str  # "completed" | "failed" | "cancelled" | "in_progress"
    results_url: str | None = None
    summary: JobSummary | None = None


class ConnectorListItem(BaseModel):
    """One connector entry in the discovery response."""

    id: str
    name: str
    description: str | None = None


class EvaluatorListItem(BaseModel):
    """One evaluator entry in the discovery response."""

    id: str
    name: str
    description: str | None = None
    scoring_dimensions: list[str] = []
