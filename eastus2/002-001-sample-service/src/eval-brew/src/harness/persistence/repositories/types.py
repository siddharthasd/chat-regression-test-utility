"""TypedDict payloads accepted by the repository ``create`` methods."""

from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict


class UtteranceCreateData(TypedDict):
    utterance_text: str
    test_id: str
    row_index: int
    extra_metadata: NotRequired[dict | None]


class EvaluationResultCreateData(TypedDict):
    utterance_id: str
    test_id: str
    evaluation_timestamp: datetime
    result_id: NotRequired[str]
    raw_chatbot_response: NotRequired[dict | None]
    normalized_contract: NotRequired[dict | None]
    evaluation_agent_id: NotRequired[str | None]
    evaluation_verdict: NotRequired[str | None]
    evaluation_scores: NotRequired[list | None]
    result_metadata: NotRequired[dict | None]
    harness_annotations: NotRequired[dict | None]
    utterance_intent: NotRequired[str | None]
    error_status: NotRequired[str | None]
    error_stage: NotRequired[str | None]
    error_details: NotRequired[str | None]
    connector_token_count: NotRequired[int | None]
    evaluator_token_count: NotRequired[int | None]
    total_token_count: NotRequired[int | None]


class ConnectorRegistrationCreateData(TypedDict):
    display_name: str
    endpoint_url: str
    auth_descriptor: dict
    connector_id: NotRequired[str]
    description: NotRequired[str | None]
    timeout_seconds: NotRequired[int]
    expects_per_row_password: NotRequired[bool]


class ConnectorRegistrationUpdateData(TypedDict, total=False):
    display_name: str
    description: str | None
    endpoint_url: str
    auth_descriptor: dict
    timeout_seconds: int
    expects_per_row_password: bool


class EvaluationAgentRegistrationCreateData(TypedDict):
    display_name: str
    endpoint_url: str
    description: NotRequired[str]
    auth_descriptor: dict
    evaluation_agent_id: NotRequired[str]
    timeout_seconds: NotRequired[int]
    declared_scoring_dimensions: NotRequired[list]


class EvaluationAgentRegistrationUpdateData(TypedDict, total=False):
    display_name: str
    description: str
    endpoint_url: str
    auth_descriptor: dict
    timeout_seconds: int
    declared_scoring_dimensions: list
