# Contract: Evaluator Client API

**Module**: `harness.evaluator`
**Stability**: Internal-stable — consumed by the orchestrator (`012`) per row.

---

## Public API

```python
VERDICTS = {"pass", "fail", "warn"}

@dataclass(frozen=True)
class EvaluatorSnapshot:
    evaluation_agent_id: str
    endpoint_url: str
    auth_descriptor: dict              # ciphertext subfields (from Job snapshot)
    timeout_seconds: int
    declared_scoring_dimensions: list[str]

@dataclass(frozen=True)
class EvaluatorResult:
    ok: bool
    evaluation_result: dict | None = None     # evaluator-emitted, validated
    harness_annotations: dict | None = None   # {"unexpected_score_dimensions": [...]}
    error_stage: str | None = None            # evaluator_auth|transport|response|result
    error_details: str | None = None
    status_code: int | None = None

def dispatch_evaluation(
    snapshot: EvaluatorSnapshot,
    contract: dict,
    *,
    client: httpx.Client | None = None,
) -> EvaluatorResult:
    """POST the contract instance to the evaluator; validate the EvaluationResult
    (FR-005b), derive harnessAnnotations, or return a categorized failure.
    Decrypts the credential just-in-time; enforces timeout; never retries; never
    caches (FR-018). `client` injectable for MockTransport tests."""

def validate_evaluation_result(body: object, *, expected_utterance_id: str) -> list[str]:
    """Return a list of FR-005b problems (empty ⇒ valid)."""

def compute_harness_annotations(scores: list, declared_dimensions: list[str]) -> dict:
    """{"unexpected_score_dimensions": [...]} — emitted names not declared (FR-005a)."""

def build_auth_headers(descriptor: dict) -> dict[str, str]:
    """4 modes (FR-007); unknown → ValueError. (Mirrors 007; dedup at integration.)"""
```

## `EvaluatorRegistryReader(session)` (FR-008–013)

```python
def list_active() -> list[EvaluatorListEntry]
    # (evaluation_agent_id, display_name, description, declared_scoring_dimensions); excludes archived.
def get(evaluation_agent_id: str) -> EvaluationAgentRegistration | None
def get_declared_dimensions(evaluation_agent_id: str) -> list[str]   # SC-011
```

## Invariants

1. `dispatch_evaluation` issues exactly one HTTP request (zero if decrypt fails first); never retries, never caches (SC-006, FR-018).
2. `ok is True` ⟺ a 200 body passed `validate_evaluation_result` (empty problem list).
3. The request body is the contract instance verbatim; no password is ever sent to the evaluator (FR-017).
4. Decrypted credential plaintext exists only within `dispatch_evaluation`; never returned/logged/stored (FR-015).
5. `evaluationAgentId` mismatch does not fail the row (soft warning); only the FR-005b checks hard-reject.
6. `harness_annotations` is harness-derived and never merged into the evaluator's `metadata`.
