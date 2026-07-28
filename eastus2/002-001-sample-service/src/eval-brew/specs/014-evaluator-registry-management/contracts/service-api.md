# Contract: EvaluatorRegistryService API

**Module**: `harness.evaluator_registry.service`
**Stability**: Internal — consumed by the `014` Flask blueprint; framework-agnostic (testable over a `Session`). Mirrors `013`'s `ConnectorRegistryService`.

---

```python
@dataclass(frozen=True)
class TestConnectionResult:
    ok: bool
    category: str          # valid|invalid_result|http_error|unreachable|timeout|auth_decrypt_failed
    status_code: int | None = None
    detail: str = ""
    warning: str | None = None   # dimension-divergence soft warning (FR-029)

class RegistrationInUseError(Exception):
    def __init__(self, evaluation_agent_id: str, job_count: int) -> None: ...

class EvaluatorRegistryService:
    def __init__(self, session: Session) -> None: ...
    def list_registrations(self, *, filter: str = "active", q: str | None = None) -> list[EvaluationAgentRegistration]
    def get(self, evaluation_agent_id: str) -> EvaluationAgentRegistration | None
    def get_auth_descriptor_decrypted(self, evaluation_agent_id: str) -> dict
    def create(self, payload: dict) -> EvaluationAgentRegistration          # FR-003
    def update(self, evaluation_agent_id: str, payload: dict, *, replace_credential: bool) -> EvaluationAgentRegistration  # FR-006/016/017
    def archive(self, evaluation_agent_id: str) -> None                     # FR-019
    def restore(self, evaluation_agent_id: str) -> None                     # FR-021
    def count_referencing_jobs(self, evaluation_agent_id: str) -> int       # JobRepository.count_by_evaluation_agent_id
    def hard_delete(self, evaluation_agent_id: str) -> None                 # FR-024; raises RegistrationInUseError
```

## `forms.parse_evaluator_form(form, *, require_credential=True) -> tuple[dict | None, dict[str,str]]`

Enforces FR-002/004/005 + dimension rules (FR-007–011): `description` required; `dimensions` parsed from a newline textarea (trim, drop blanks, preserve order); `payload["declared_scoring_dimensions"]` is the ordered list; `payload["auth_descriptor"]` uses canonical `credential`/`password` keys. Returns `(payload, errors)`; a duplicate-dimension condition is a non-blocking warning surfaced separately (not in `errors`).

## `test_connection.run_test_connection(endpoint_url, decrypted_descriptor, timeout_seconds, declared_dimensions, *, client=None) -> TestConnectionResult`

POSTs a fixed sample contract (`harness.connector.mock.build_contract` with `utteranceId="test-utt"`) with the auth header; validates a 2xx body via `harness.evaluator.validate_evaluation_result(body, expected_utterance_id="test-utt")`; soft-warns via `harness.evaluator.compute_harness_annotations` when emitted dimensions diverge from `declared_dimensions` (FR-026–030). Never persists. `client` injectable.

## Invariants

1. `create`/`update` never store plaintext credentials (SC-002).
2. `update` without `replace_credential` and without a mode change preserves the stored ciphertext.
3. Declared dimensions persist + read back in exact saved order (SC-011).
4. `hard_delete` refused while any Job snapshot references the `evaluation_agent_id` (SC-007).
5. `run_test_connection` performs no writes; validates the response as an EvaluationResult, not a contract (SC-009/010).
6. Read access for other modules is `harness.evaluator.EvaluatorRegistryReader` (FR-031), not re-implemented.
